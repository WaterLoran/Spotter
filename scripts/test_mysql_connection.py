#!/usr/bin/env python3
"""
用与 Spotter 后端相同的 PyMySQL 栈探测 MySQL 是否可达（排除「前端 Network Error」其实是后端未起等问题）。

默认参数对应常见本机若依库（可按需改）：
  127.0.0.1:33060 / ruoyi / root / ruoyi123

用法:
  cd backend && source .venv/bin/activate
  python ../scripts/test_mysql_connection.py

  python ../scripts/test_mysql_connection.py --port 3306 --password 'xxx'

若依 RuoYi 的 JDBC 须与真实端口一致，例如:
  jdbc:mysql://127.0.0.1:33060/ruoyi?...
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    p = argparse.ArgumentParser(description="测试 MySQL TCP + 登录 + 选库（Spotter / 若依 排障）")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=33060)
    p.add_argument("--database", default="ruoyi")
    p.add_argument("--user", default="root")
    p.add_argument("--password", default="ruoyi123")
    args = p.parse_args()

    try:
        import pymysql
    except ImportError:
        print("未安装 pymysql。在 backend 虚拟环境中执行: pip install pymysql", file=sys.stderr)
        return 2

    print(f"连接: {args.user}@{args.host}:{args.port}/{args.database} ...")
    try:
        conn = pymysql.connect(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database,
            connect_timeout=10,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION() AS version, DATABASE() AS db, USER() AS u")
                row = cur.fetchone()
            print("成功.")
            print(f"  MySQL: {row[0]}")
            print(f"  当前库: {row[1]}")
            print(f"  登录用户: {row[2]}")
        finally:
            conn.close()
    except pymysql.err.OperationalError as e:
        code, msg = e.args[0], e.args[1] if len(e.args) > 1 else str(e)
        print(f"失败 (OperationalError {code}): {msg}", file=sys.stderr)
        print(
            "\n常见原因:\n"
            "  - MySQL 未启动或端口不对（你配置的是 33060，若依里 jdbc 也必须是 33060，不能写 3306）\n"
            "  - 库名不存在: 先建库 CREATE DATABASE ruoyi ... 并导入 SQL\n"
            "  - 用户/密码错误\n",
            file=sys.stderr,
        )
        return 1
    except OSError as e:
        print(f"失败 (网络/系统): {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
