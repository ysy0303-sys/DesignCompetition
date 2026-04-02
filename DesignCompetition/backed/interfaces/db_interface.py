# interfaces/db_interface.py

class DBInterface:

    def get_user_basic(self, user_id):
        """
        返回:
        {
            "major": str,
            "grade": int
        }
        """
        raise NotImplementedError

    def get_user_gpa(self, user_id):
        """
        返回 float
        """
        raise NotImplementedError

    def get_latest_state(self, user_id):
        """
        返回:
        {
            "brain_score": int,
            "state_tag": str
        }
        """
        raise NotImplementedError

    def get_unfinished_task_count(self, user_id):
        """
        返回 int
        """
        raise NotImplementedError