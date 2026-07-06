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
    confirming = State()

class ReportPeriod(StatesGroup):
    waiting_for_start = State()
    waiting_for_end = State()

class SelectObjectState(StatesGroup):
    waiting = State()

class GoogleDriveSetup(StatesGroup):
    waiting_for_folder_id = State()

class DeleteConfirm(StatesGroup):
    waiting = State()
