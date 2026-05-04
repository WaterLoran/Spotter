from sqleye.models import Session


def get_workspace_session(db, system_id):
    """Return first SQL workspace session for legacy callers."""
    return db.query(Session).filter(Session.system_id == int(system_id)).order_by(Session.id.asc()).first()


def get_session_by_id(db, system_id, session_id):
    if session_id is None:
        return None
    try:
        sid = int(session_id)
    except (TypeError, ValueError):
        return None
    return db.query(Session).filter(Session.id == sid, Session.system_id == int(system_id)).first()


def first_session_for_system(db, system_id):
    return db.query(Session).filter(Session.system_id == int(system_id)).order_by(Session.id.asc()).first()
