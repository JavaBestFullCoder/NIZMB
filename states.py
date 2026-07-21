from aiogram.fsm.state import State, StatesGroup

class Registration(StatesGroup):
    waiting_for_code = State()

class AddObject(StatesGroup):
    waiting_for_name = State()
    waiting_for_code = State()

class AddEmployee(StatesGroup):
    waiting_for_name = State()
    waiting_for_code = State()

class AddIncome(StatesGroup):
    waiting_for_amount = State()
    waiting_for_date = State()

class AddExpense(StatesGroup):
    waiting_for_amount = State()
    waiting_for_reason = State()
    waiting_for_date = State()

class Transfer(StatesGroup):
    waiting_for_amount = State()
    confirming = State()

class ReportPeriod(StatesGroup):
    waiting_for_start = State()
    waiting_for_end = State()

class SelectObjectState(StatesGroup):
    waiting = State()

class AddHQUser(StatesGroup):
    waiting_for_name = State()
    waiting_for_code = State()

class DeleteConfirm(StatesGroup):
    waiting = State()

class DeleteOperation(StatesGroup):
    waiting_for_id = State()
    waiting_for_reason = State()

class DeleteHQUser(StatesGroup):
    waiting = State()
