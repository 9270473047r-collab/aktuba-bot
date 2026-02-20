
from aiogram.fsm.state import State, StatesGroup

class TaskFSM(StatesGroup):
    choose_action = State()
    title = State()
    description = State()
    assignee = State()
    deadline = State()

class AcceptFSM(StatesGroup):
    waiting_for_report = State()
    waiting_for_prolong_date = State()
    waiting_for_accept_deadline = State()
    waiting_for_reject_comment = State()
    waiting_for_delegate_target = State()
