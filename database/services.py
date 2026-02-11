from .connection import SessionLocal
from .models import User

def add_user(user_id: int, username: str, full_name: str):
    session = SessionLocal()
    try:
        existing_user = session.query(User).filter(User.id == user_id).first()
        
        if not existing_user:
            new_user = User(
                id=user_id,
                username=username,
                full_name=full_name
            )
            session.add(new_user)
            session.commit()
            return True 
        return False 
    except Exception as e:
        session.rollback()
        print(f"Error adding user: {e}")
    finally:
        session.close()

def get_all_users_id():
    session = SessionLocal()
    try:
        users = session.query(User.id).all()
        return [user.id for user in users]
    finally:
        session.close()

def count_users():
    session = SessionLocal()
    try:
        return session.query(User).count()
    finally:
        session.close()