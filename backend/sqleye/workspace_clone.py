"""Clone SQL workspace (session, query tasks, field search tasks) between systems. Does not copy query history."""

from sqleye.db import SessionLocal
from sqleye.models import FieldSearchTask, QueryTask, Session


def copy_sql_workspace(source_system_id: int, target_system_id: int) -> None:
    db = SessionLocal()
    try:
        src = db.query(Session).filter(Session.system_id == int(source_system_id)).first()
        if not src:
            return
        if db.query(Session).filter(Session.system_id == int(target_system_id)).first():
            return
        dst = Session(
            system_id=int(target_system_id),
            name=src.name,
            db_type=src.db_type,
            host=src.host,
            port=src.port,
            username=src.username,
            password=src.password,
            database=src.database,
        )
        db.add(dst)
        db.flush()
        for qt in db.query(QueryTask).filter(QueryTask.session_id == src.id).all():
            db.add(
                QueryTask(
                    session_id=dst.id,
                    name=qt.name,
                    sql=qt.sql,
                    polling_interval=qt.polling_interval,
                    is_active=qt.is_active,
                )
            )
        for ft in db.query(FieldSearchTask).filter(FieldSearchTask.session_id == src.id).all():
            db.add(
                FieldSearchTask(
                    session_id=dst.id,
                    name=ft.name,
                    expression=ft.expression,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
