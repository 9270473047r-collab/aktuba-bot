from db import db

ADMIN_USER_ID = 409710353  # Твой user_id

def delete_all_users_except_admin():
    # TODO: переписать на async
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE user_id != ?", (ADMIN_USER_ID,))
        conn.commit()
        print("Все пользователи, кроме администратора, удалены.")

if __name__ == "__main__":
    delete_all_users_except_admin()
