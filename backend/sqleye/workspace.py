from sqleye.models import Session


def get_workspace_session(db, system_id):
    return db.query(Session).filter(Session.system_id == int(system_id)).first()
