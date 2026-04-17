import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS

from config import APP_LOG_PATH, DEBUG, HOST, PORT, SCHEDULER_ENABLED, SCHEDULER_SEARCH_CONFIG_INTERVAL_SECONDS
from fastlog import database
from fastlog.init_progress import progress_manager

try:
    from fastlog.log_collector import LogCollector
    from fastlog.scheduler import DaemonManager
    from fastlog.shell_query_service import ShellQueryService
except Exception:  # pragma: no cover
    LogCollector = None
    DaemonManager = None
    ShellQueryService = None

try:
    from sqleye.routes_field_search import field_search_bp
    from sqleye.routes_queries import sql_queries_bp
    from sqleye.routes_sessions import sql_sessions_bp
except Exception:  # pragma: no cover
    field_search_bp = None
    sql_queries_bp = None
    sql_sessions_bp = None


def ok(data=None, message=""):
    return jsonify({"success": True, "message": message, "data": data})


def err(message, code=400):
    return jsonify({"success": False, "error": message}), code


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/")
    CORS(app)
    database.init_db()
    setup_logging(app)

    @app.before_request
    def load_system_id():
        value = request.headers.get("X-FastLog-System-Id", "1")
        try:
            g.system_id = int(value)
        except ValueError:
            g.system_id = 1

    if sql_sessions_bp:
        app.register_blueprint(sql_sessions_bp, url_prefix="/api/sql")
    if sql_queries_bp:
        app.register_blueprint(sql_queries_bp, url_prefix="/api/sql")
    if field_search_bp:
        app.register_blueprint(field_search_bp, url_prefix="/api/sql")

    register_routes(app)
    start_background_services(app)
    return app


def setup_logging(app):
    APP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    file_handler = RotatingFileHandler(APP_LOG_PATH, maxBytes=50 * 1024 * 1024, backupCount=10)
    file_handler.setFormatter(fmt)

    # Also stream to stdout so docker logs / terminal shows daemon activity.
    import sys
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(stream_handler)

    # fastlog.* (SSH / 守护采集) 写到同一文件 + 控制台，便于实时排查
    fl = logging.getLogger("fastlog")
    fl.setLevel(logging.INFO)
    fl.addHandler(file_handler)
    fl.addHandler(stream_handler)
    fl.propagate = False


def start_background_services(app):
    app.extensions["log_processor"] = LogCollector() if LogCollector else None
    # Always attach DaemonManager when LogCollector is available so that POST /api/reinitialize
    # can ensure_daemon() even if SCHEDULER_ENABLED is false (common in local dev). Otherwise
    # "重新初始化" would clear logs but no background thread would ever collect again.
    if DaemonManager and app.extensions["log_processor"]:
        daemon_manager = DaemonManager(app.extensions["log_processor"])
        app.extensions["daemon_manager"] = daemon_manager
        if SCHEDULER_ENABLED:
            daemon_manager.start()
        app.logger.info(
            "start_background_services: daemon_manager=%s SCHEDULER_ENABLED=%s auto_start=%s",
            bool(daemon_manager),
            SCHEDULER_ENABLED,
            SCHEDULER_ENABLED,
        )
    else:
        app.logger.warning(
            "start_background_services: no daemon_manager (DaemonManager=%s log_processor=%s)",
            bool(DaemonManager),
            bool(app.extensions.get("log_processor")),
        )
    if ShellQueryService:
        app.extensions["shell_service"] = ShellQueryService()


def register_routes(app):
    @app.get("/api/health")
    def health():
        return ok({"status": "ok"})

    @app.get("/api/config")
    def get_config():
        return ok(database.get_config(g.system_id))

    @app.post("/api/config")
    def post_config():
        payload = request.get_json(silent=True) or {}
        database.update_config(g.system_id, payload)
        return ok(message="配置已更新")

    @app.post("/api/config/apply")
    def apply_config():
        """Save config and ensure the daemon is (re)started so continuous collection begins immediately."""
        payload = request.get_json(silent=True) or {}
        system_id = int(g.system_id)
        if payload:
            database.update_config(system_id, payload)
        dm = app.extensions.get("daemon_manager")
        if not dm:
            return err("后台任务管理器不可用", 503)
        dm.ensure_daemon(system_id)
        snap = dm.status_snapshot()
        app.logger.info(
            "apply_config: system_id=%s daemon restarted, scheduler_running=%s",
            system_id,
            snap.get("scheduler_running"),
        )
        return ok(
            {
                "scheduler_running": snap.get("scheduler_running", False),
                "daemon_count": snap.get("daemon_count", 0),
            },
            message="配置已保存，日志采集已启动",
        )

    @app.post("/api/test-connection")
    def test_connection():
        proc = app.extensions.get("log_processor")
        if not proc:
            return err("日志处理器不可用", 503)
        payload = request.get_json(silent=True) or {}
        allowed = {"server_host", "server_username", "server_password", "server_port"}
        cfg_override = {k: payload.get(k) for k in allowed if k in payload}
        result = proc.test_connection(g.system_id, cfg_override=cfg_override)
        app.logger.info(
            "test_connection system_id=%s ok=%s keys_override=%s",
            g.system_id,
            (result or {}).get("ok"),
            list(cfg_override.keys()),
        )
        return ok(result)

    @app.post("/api/reinitialize")
    def reinitialize():
        proc = app.extensions.get("log_processor")
        if not proc:
            return err("日志处理器不可用", 503)
        task_id = progress_manager.create_task()
        system_id = int(g.system_id)
        # Reinitialize means a full rebuild from remote logs.
        # Clear local logs first to avoid mixing old/new snapshots.
        deleted = database.clear_logs(system_id)
        dm = app.extensions.get("daemon_manager")
        app.logger.info(
            "reinitialize: system_id=%s task_id=%s cleared_logs=%s daemon_manager=%s",
            system_id,
            task_id,
            deleted,
            dm is not None,
        )
        if dm:
            dm.ensure_daemon(system_id)
            app.logger.info("reinitialize: ensure_daemon done system_id=%s", system_id)
        else:
            app.logger.warning("reinitialize: no daemon_manager — background collection will not run")

        def runner():
            with app.app_context():
                try:
                    app.logger.info("reinitialize worker: initialize start system_id=%s task_id=%s", system_id, task_id)
                    finished = proc.initialize(system_id, task_id=task_id)
                    if finished:
                        progress_manager.complete_task(task_id)
                        app.logger.info(
                            "reinitialize worker: initialize completed system_id=%s task_id=%s",
                            system_id,
                            task_id,
                        )
                    else:
                        progress_manager.mark_cancelled(task_id)
                        app.logger.warning(
                            "reinitialize worker: initialize cancelled system_id=%s task_id=%s",
                            system_id,
                            task_id,
                        )
                except Exception as ex:
                    app.logger.exception("reinitialize worker: initialize failed system_id=%s", system_id)
                    progress_manager.fail_task(task_id, ex)

        threading.Thread(target=runner, daemon=True).start()
        return ok({"task_id": task_id})

    @app.get("/api/reinitialize/progress/<task_id>")
    def reinitialize_progress(task_id):
        return ok(progress_manager.get_task(task_id))

    @app.post("/api/reinitialize/cancel/<task_id>")
    def reinitialize_cancel(task_id):
        if progress_manager.cancel_task(task_id):
            return ok({"task_id": task_id, "cancel_requested": True}, "已请求停止初始化")
        return err("任务不存在或已结束", 404)

    @app.get("/api/logs")
    def list_logs():
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
        search = request.args.get("search", "")
        notes_only = request.args.get("notes_only", "false").lower() == "true"
        return ok(database.list_logs(g.system_id, page, page_size, search, notes_only))

    @app.delete("/api/logs")
    def clear_logs():
        deleted = database.clear_logs(g.system_id)
        return ok({"deleted": deleted}, message="日志已清空")

    @app.delete("/api/logs/<int:log_id>")
    def remove_log(log_id):
        if not database.delete_log(g.system_id, log_id):
            return err("日志不存在或无权删除", 404)
        return ok(message="日志已删除")

    @app.put("/api/logs/<int:log_id>/notes")
    def edit_log_note(log_id):
        payload = request.get_json(silent=True) or {}
        if not database.update_log_notes(g.system_id, log_id, payload.get("notes", "")):
            return err("日志不存在或无权更新", 404)
        return ok(message="备注已更新")

    @app.put("/api/logs/notes")
    def edit_log_notes():
        payload = request.get_json(silent=True) or {}
        database.bulk_update_log_notes(
            g.system_id,
            payload.get("log_ids", []),
            payload.get("notes", ""),
            append=bool(payload.get("append")),
            only_empty=bool(payload.get("only_empty")),
        )
        return ok(message="批量备注已更新")

    @app.post("/api/logs/dedupe-by-content")
    def dedupe_logs():
        deleted = database.dedupe_logs_by_content(g.system_id)
        return ok({"deleted": deleted})

    @app.post("/api/logs/append")
    def append_logs():
        proc = app.extensions.get("log_processor")
        if not proc:
            return err("日志处理器不可用", 503)
        task_id = progress_manager.create_task()
        raw = request.get_json(silent=True) or {}
        payload = {k: raw[k] for k in ("search_text", "time_range_minutes") if k in raw}
        system_id = int(g.system_id)
        # 手动一次性追加（调度器不用此接口）。在请求线程快照配置，避免后台执行时配置已变。
        cfg_snapshot = dict(database.get_config(system_id))

        def runner():
            with app.app_context():
                try:
                    finished = proc.append_logs(
                        system_id,
                        payload,
                        task_id=task_id,
                        use_main_log_config=True,
                        cfg_snapshot=cfg_snapshot,
                    )
                    if finished:
                        progress_manager.complete_task(task_id)
                    else:
                        progress_manager.mark_cancelled(task_id)
                except Exception as ex:
                    progress_manager.fail_task(task_id, ex)

        threading.Thread(target=runner, daemon=True).start()
        return ok({"task_id": task_id})

    @app.get("/api/logs/append/progress/<task_id>")
    def append_logs_progress(task_id):
        return ok(progress_manager.get_task(task_id))

    @app.post("/api/logs/append/cancel/<task_id>")
    def append_logs_cancel(task_id):
        if progress_manager.cancel_task(task_id):
            return ok({"task_id": task_id, "cancel_requested": True}, "已请求停止追加日志")
        return err("任务不存在或已结束", 404)

    @app.get("/api/systems")
    def get_systems():
        return ok(database.list_systems())

    @app.post("/api/systems")
    def post_system():
        payload = request.get_json(silent=True) or {}
        new_id, source_id = database.create_system(payload.get("name", "新系统"))
        dm = app.extensions.get("daemon_manager")
        if dm:
            dm.ensure_daemon(int(new_id))
        if source_id is not None and sql_sessions_bp:
            try:
                from sqleye.workspace_clone import copy_sql_workspace

                copy_sql_workspace(source_id, new_id)
            except Exception as ex:
                app.logger.exception("copy_sql_workspace failed after create_system")
                try:
                    database.delete_system(new_id)
                except ValueError:
                    pass
                return err(f"创建系统失败（SQL 工作区复制错误）: {ex}", 500)
        return ok({"id": new_id})

    @app.put("/api/systems/<int:system_id>")
    def put_system(system_id):
        payload = request.get_json(silent=True) or {}
        database.rename_system(system_id, payload.get("name", "未命名系统"))
        return ok(message="系统已重命名")

    @app.delete("/api/systems/<int:system_id>")
    def remove_system(system_id):
        try:
            database.delete_system(system_id)
        except ValueError as ex:
            return err(str(ex), 400)
        dm = app.extensions.get("daemon_manager")
        if dm:
            dm.stop_daemon(system_id)
        return ok(message="系统已删除")

    @app.get("/api/search-configs")
    def get_search_configs():
        return ok(database.list_search_configs(g.system_id))

    @app.post("/api/search-configs")
    def post_search_config():
        payload = request.get_json(silent=True) or {}
        cfg_id = database.create_search_config(g.system_id, payload)
        return ok({"id": cfg_id})

    @app.put("/api/search-configs/<int:cfg_id>")
    def put_search_config(cfg_id):
        payload = request.get_json(silent=True) or {}
        database.update_search_config(g.system_id, cfg_id, payload)
        return ok(message="配置已更新")

    @app.delete("/api/search-configs/<int:cfg_id>")
    def remove_search_config(cfg_id):
        database.delete_search_config(g.system_id, cfg_id)
        return ok(message="配置已删除")

    @app.post("/api/search-configs/execute")
    def execute_search_configs():
        proc = app.extensions.get("log_processor")
        if not proc:
            return err("日志处理器不可用", 503)
        task_id = progress_manager.create_task()
        system_id = int(g.system_id)

        def runner():
            with app.app_context():
                try:
                    proc.execute_search_configs(system_id, task_id=task_id)
                    progress_manager.complete_task(task_id)
                except Exception as ex:
                    progress_manager.fail_task(task_id, ex)

        threading.Thread(target=runner, daemon=True).start()
        return ok({"task_id": task_id})

    @app.get("/api/search-configs/execute/progress/<task_id>")
    def execute_search_progress(task_id):
        return ok(progress_manager.get_task(task_id))

    @app.get("/api/log-views")
    def get_log_views():
        return ok(database.list_log_views(g.system_id))

    @app.post("/api/log-views")
    def post_log_view():
        payload = request.get_json(silent=True) or {}
        view_id = database.create_log_view(g.system_id, payload)
        return ok({"id": view_id})

    @app.put("/api/log-views/<int:view_id>")
    def put_log_view(view_id):
        payload = request.get_json(silent=True) or {}
        database.update_log_view(g.system_id, view_id, payload)
        return ok(message="视图已更新")

    @app.delete("/api/log-views/<int:view_id>")
    def remove_log_view(view_id):
        database.delete_log_view(g.system_id, view_id)
        return ok(message="视图已删除")

    @app.get("/api/log-views/<int:view_id>/timeline-notes")
    def get_timeline_notes(view_id):
        return ok(database.list_timeline_notes(view_id))

    @app.post("/api/log-views/<int:view_id>/timeline-notes")
    def post_timeline_note(view_id):
        payload = request.get_json(silent=True) or {}
        note_id = database.create_timeline_note(
            view_id,
            payload.get("title", ""),
            payload.get("content", ""),
            payload.get("tags", []),
        )
        return ok({"id": note_id})

    @app.put("/api/log-views/timeline-notes/<int:note_id>")
    def put_timeline_note(note_id):
        payload = request.get_json(silent=True) or {}
        database.update_timeline_note(note_id, payload)
        return ok(message="备注已更新")

    @app.delete("/api/log-views/timeline-notes/<int:note_id>")
    def remove_timeline_note(note_id):
        database.delete_timeline_note(note_id)
        return ok(message="备注已删除")

    @app.get("/api/shell/queries")
    def get_shell_queries():
        return ok(database.list_shell_queries(g.system_id))

    @app.post("/api/shell/queries")
    def post_shell_query():
        payload = request.get_json(silent=True) or {}
        query_id = database.create_shell_query(g.system_id, payload)
        return ok({"id": query_id})

    @app.put("/api/shell/queries/<int:query_id>")
    def put_shell_query(query_id):
        payload = request.get_json(silent=True) or {}
        database.update_shell_query(g.system_id, query_id, payload)
        return ok(message="任务已更新")

    @app.delete("/api/shell/queries/<int:query_id>")
    def remove_shell_query(query_id):
        try:
            database.delete_shell_query(g.system_id, query_id)
        except ValueError as ex:
            return err(str(ex), 400)
        return ok(message="任务已删除")

    @app.post("/api/shell/queries/<int:query_id>/execute")
    def execute_shell_query(query_id):
        service = app.extensions.get("shell_service")
        if not service:
            return err("Shell 服务不可用", 503)
        result = service.execute_query(g.system_id, query_id)
        return ok(result)

    @app.get("/api/shell/queries/<int:query_id>/history")
    def shell_query_history(query_id):
        return ok(database.list_shell_query_history(query_id))

    @app.delete("/api/shell/queries/<int:query_id>/history/<int:hid>")
    def delete_shell_history(query_id, hid):
        database.delete_shell_query_history(hid)
        return ok(message="历史记录已删除")

    @app.get("/api/shell/presets")
    def shell_presets():
        return ok(
            [
                {"name": "查看进程数", "command": "ps aux | wc -l", "polling_interval": 60},
                {"name": "磁盘使用情况", "command": "df -h", "polling_interval": 300},
                {
                    "name": "最近系统错误日志",
                    "command": "tail -n 100 /var/log/syslog | grep -i error || echo 'no syslog or errors found'",
                    "polling_interval": 120,
                },
            ]
        )

    @app.get("/api/background-tasks")
    def background_tasks():
        dm = app.extensions.get("daemon_manager")
        shell_service = app.extensions.get("shell_service")
        snap = dm.status_snapshot() if dm else {}
        return ok(
            {
                "scheduler_running": snap.get("scheduler_running", False),
                "scheduler_interval": snap.get("interval_seconds", 0),
                "scheduler_search_config_interval": getattr(
                    dm, "search_config_interval_seconds", SCHEDULER_SEARCH_CONFIG_INTERVAL_SECONDS
                )
                if dm
                else SCHEDULER_SEARCH_CONFIG_INTERVAL_SECONDS,
                "last_scheduler_tick_at": snap.get("last_tick_at"),
                "last_main_inserted_total": snap.get("last_main_inserted_total", 0),
                "last_tick_ran_search_configs": True,
                "last_scheduler_error": snap.get("last_scheduler_error"),
                "last_scheduler_error_system_id": snap.get("last_scheduler_error_system_id"),
                "last_scheduler_error_at": snap.get("last_scheduler_error_at"),
                "daemon_count": snap.get("daemon_count", 0),
                "sql_polling_tasks": [],
                "shell_polling_tasks": shell_service.list_polling_tasks() if shell_service else [],
            }
        )

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path):
        static_folder = Path(app.static_folder or "")
        if path and (static_folder / path).exists():
            return send_from_directory(static_folder, path)
        index_file = static_folder / "index.html"
        if index_file.exists():
            return send_from_directory(static_folder, "index.html")
        return ok({"message": "Spotter backend is running"})


app = create_app()

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)

