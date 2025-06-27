from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, Message, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from datetime import datetime, timedelta
import asyncio
import os
from dotenv import load_dotenv
import sqlite3
from admin import router as admin_router

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        reminded INTEGER DEFAULT 0
    )
''')
conn.commit()


load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class BookingStates(StatesGroup):
    START_MENU = State()
    MAIN_MENU = State()
    WAITING_FOR_DATE = State()
    WAITING_FOR_TIME = State()
    WAITING_FOR_NAME = State()
    WAITING_FOR_PHONE = State()
    WAITING_FOR_CONFIRMATION = State()
    

# START MENU — показывается только при /start
start_menu = ReplyKeyboardBuilder()
start_menu.button(text="Send a Request")

# MAIN MENU — показывается после завершения записи
M_menu = ReplyKeyboardBuilder()
M_menu.button(text="📋 View my last appointment")
M_menu.button(text="📜 View booking history")
M_menu.button(text="➕ New booking")
M_menu.button(text="❌ Cancel my appointment")
M_menu.adjust(1)


def get_date_keyboard():
    today = datetime.now().date()
    now_time = datetime.now().time()
    buttons = []
    all_times = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"]

    valid_days_found = 0
    current_day = today

    while valid_days_found < 7:
        if current_day.weekday() < 6:  # Понедельник–Суббота
            booked_times = get_booked_times(current_day.strftime('%Y-%m-%d'))

            available_times = []
            for t in all_times:
                if t in booked_times:
                    continue

                if current_day == today:
                    slot_time = datetime.strptime(t, "%H:%M").time()
                    if slot_time <= now_time:
                        continue

                available_times.append(t)

            if available_times:
                slots_count = len(available_times)
                if slots_count == 1:
                    label = f"{current_day.strftime('%d.%m.%Y')} (1 time left)"
                else:
                    label = f"{current_day.strftime('%d.%m.%Y')} ({slots_count} times left)"
                
                callback = f"date:{current_day.strftime('%Y-%m-%d')}"
                buttons.append([InlineKeyboardButton(text=label, callback_data=callback)])
                valid_days_found += 1

        current_day += timedelta(days=1)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_time_keyboard(selected_date):
    all_times = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"]
    booked = get_booked_times(selected_date.strftime('%Y-%m-%d'))

    now = datetime.now()
    today = now.date()
    current_time = now.time()

    buttons = []
    for t in all_times:
        time_obj = datetime.strptime(t, "%H:%M").time()

        # ⛔ skip booked times
        if t in booked:
            continue

        # ⛔ skip past times and times less than 1 hour from now
        if selected_date == today and datetime.combine(today, time_obj) <= now + timedelta(hours=1):
            continue

        # ✅ add button
        buttons.append([InlineKeyboardButton(text=t, callback_data=f"time:{t}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_confirmation_keyboard():
    buttons = [
        [InlineKeyboardButton(text="✅ Yes", callback_data="confirm:yes")],
        [InlineKeyboardButton(text="🔁 Change", callback_data="confirm:change")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.set_state(BookingStates.START_MENU)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 Send a Request", callback_data="send_request")]
        ]
    )

    await message.answer(
        "👋 Hello! Welcome to our Barbershop Booking Bot!\nClick the button below to send a booking request.",
        reply_markup=keyboard
    )

# add send request validation
@dp.callback_query(F.data == "send_request")
async def handle_send_request(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup()  # ❗ Убираем inline-кнопку из старого сообщения
    await callback.message.answer(
        "Please select a date for your appointment:",
        reply_markup=get_date_keyboard()
    )
    await state.set_state(BookingStates.WAITING_FOR_DATE)
    await callback.answer()


# add date validation
@dp.callback_query(F.data.startswith("date:"))
async def process_date(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup()  # Убираем inline-кнопки
    date_str = callback.data.split(":")[1]
    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    await state.update_data(date=date, target="date")
    await callback.message.answer(
        f"You selected the date: {date.strftime('%d.%m.%Y')}\nIs it correct?",
        reply_markup=get_confirmation_keyboard()
    )
    await state.set_state(BookingStates.WAITING_FOR_CONFIRMATION)

# add time validation
@dp.callback_query(F.data.startswith("time:"))
async def process_time(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup()  # Убираем inline-кнопки
    time_str = callback.data.removeprefix("time:")
    time = datetime.strptime(time_str, "%H:%M").time()

    await state.update_data(time=time, target="time")
    await callback.message.answer(f"You selected the time: {time_str}\nIs it correct?", reply_markup=get_confirmation_keyboard())
    await state.set_state(BookingStates.WAITING_FOR_CONFIRMATION)

# add name validation
@dp.message(BookingStates.WAITING_FOR_NAME)
async def process_name(message: Message, state:FSMContext):
    name = message.text.strip()
    if not name.isalpha():
        await message.answer("Name should contain only letters. Please enter a valid name:")
        return
    await state.update_data(name=name, target="name")
    await message.answer(
        "Is your name correct?",
        reply_markup=get_confirmation_keyboard()
    )
    await state.set_state(BookingStates.WAITING_FOR_CONFIRMATION)

# add phone validation
@dp.message(BookingStates.WAITING_FOR_PHONE)
async def process_phone(message: Message, state:FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit() or len(phone) != 12:
        await message.answer("Phone number should start with '+' followed by 11 digits. Please enter a valid phone number:")
        return
    await state.update_data(phone=phone, target="phone")
    await message.answer(
        "Is your phone number correct?",
        reply_markup=get_confirmation_keyboard()
    )
    await state.set_state(BookingStates.WAITING_FOR_CONFIRMATION)




# add confirmation 
@dp.callback_query(F.data.startswith("confirm:"))
async def process_date_confirmation(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup()  # Убираем inline-кнопки
    answer = callback.data.split(":")[1]
    data = await state.get_data()
    target = data.get("target")

    if answer == "yes":
        if target == "date":
            selected_date = data.get("date")  # ← достаём дату из FSM
            await callback.message.answer("Now choose a time:", reply_markup=get_time_keyboard(selected_date))
            await state.set_state(BookingStates.WAITING_FOR_TIME)
            
        elif target == "time":
            await callback.message.answer("Please enter your name:")
            await state.set_state(BookingStates.WAITING_FOR_NAME)

        elif target == "name":
            await callback.message.answer("Please enter your phone number, example: +373********")
            await state.set_state(BookingStates.WAITING_FOR_PHONE)

        elif target == "phone":
            data = await state.get_data()
            date = data.get("date")
            time = data.get("time")
            name = data.get("name")
            phone = data.get("phone")

            confirmation_text = (
                f"✅ Your appointment is confirmed!\n\n"
                f"📅 Date: {date.strftime('%d.%m.%Y')}\n"
                f"⏰ Time: {time.strftime('%H:%M')}\n"
                f"👤 Name: {name}\n"
                f"📞 Phone: {phone}"
            )

            cursor.execute(
                "INSERT INTO appointments (user_id, date, time, name, phone) VALUES (?, ?, ?, ?, ?)",
                (callback.from_user.id, date.strftime('%Y-%m-%d'), time.strftime('%H:%M'), name, phone)
            )
            conn.commit()

            await callback.message.answer(confirmation_text)
            await callback.message.answer(
                "What would you like to do next?",
                reply_markup=M_menu.as_markup(resize_keyboard=True)
            )

            await state.set_state(BookingStates.MAIN_MENU)
            

    elif answer == "change":
        if target == "date":
            await callback.message.answer("Please select a date again:", reply_markup=get_date_keyboard())
            await state.set_state(BookingStates.WAITING_FOR_DATE)

        elif target == "time":
            selected_date = data.get("date")
            await callback.message.answer("Please choose a time again:", reply_markup=get_time_keyboard(selected_date))
            await state.set_state(BookingStates.WAITING_FOR_TIME)

        elif target == "name":
            await callback.message.answer("Please enter your name again:")
            await state.set_state(BookingStates.WAITING_FOR_NAME)

        elif target == "phone":
            await callback.message.answer("Please enter your phone number again:")
            await state.set_state(BookingStates.WAITING_FOR_PHONE)


    await callback.answer()

def get_booked_times(date):
    cursor.execute("SELECT time FROM appointments WHERE date = ?", (date,))
    results = cursor.fetchall()
    return [row[0] for row in results]

@dp.message(BookingStates.MAIN_MENU, F.text == "📋 View my last appointment")
async def show_last_appointment(message: Message, state: FSMContext):
    await message.answer("Your last appointment:")
    cursor.execute("SELECT * FROM appointments WHERE user_id = ? ORDER BY date DESC, time DESC LIMIT 1", (message.from_user.id,))
    result = cursor.fetchone()
    if result:
        await message.answer(f"Date: {result[2]}\nTime: {result[3]}\nName: {result[4]}\nPhone: {result[5]}")
    else:
        await message.answer("You have no appointments yet.")
    await state.set_state(BookingStates.MAIN_MENU)

@dp.message(BookingStates.MAIN_MENU, F.text == "📜 View booking history")
async def show_booking_history(message: Message, state: FSMContext):
    cursor.execute("SELECT date, time, name FROM appointments WHERE user_id = ? ORDER BY date, time", (message.from_user.id,))
    results = cursor.fetchall()

    if results:
        text_lines = [f"{row[0]}, {row[1]}, {row[2]}" for row in results]
        history_text = "\n".join(text_lines)
        await message.answer(f"🗂 Your booking history:\n\n{history_text}")
    else:
        await message.answer("You have no appointments yet.")

    await state.set_state(BookingStates.MAIN_MENU)

@dp.message(BookingStates.MAIN_MENU, F.text == "➕ New booking")
async def start_new_booking(message: Message, state: FSMContext):
    now = datetime.now()
    start_of_week = now.date() - timedelta(days=now.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    cursor.execute("""
        SELECT COUNT(*) FROM appointments
        WHERE user_id = ?
        AND date BETWEEN ? AND ?
    """, (message.from_user.id, start_of_week.strftime('%Y-%m-%d'), end_of_week.strftime('%Y-%m-%d')))
    count = cursor.fetchone()[0]

    if count >= 2:
        await message.answer("⚠️ For security reasons, each user is allowed to make up to 2 bookings per week.\nUnfortunately, you can't book more right now.")
        return
    
    await message.answer("Please select a date for your appointment:", reply_markup=get_date_keyboard())
    await state.set_state(BookingStates.WAITING_FOR_DATE)

@dp.message(BookingStates.MAIN_MENU, F.text == "❌ Cancel my appointment")
async def cancel_appointment(message: Message, state: FSMContext):
    now = datetime.now()
    today = now.date()
    current_time = now.strftime('%H:%M')
    cursor.execute("""
        SELECT * FROM appointments
        WHERE user_id = ? AND (
            date > ? OR (date = ? AND time > ?)
        )
        ORDER BY date, time
    """, (message.from_user.id, today, today, current_time))
    results = cursor.fetchall()
    if results:
        for result in results:
            appointment_id = result[0]
            date = result[2]
            time = result[3]
            name = result[4]
            phone = result[5]

            text = f"📅 Date: {date}\n⏰ Time: {time}\n👤 Name: {name}\n📞 Phone: {phone}"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Cancel this", callback_data=f"ask_cancel:{appointment_id}")]
                ]
            )
            await message.answer(text, reply_markup=keyboard)
    else:
        await message.answer("You don't have any upcoming appointments.")
    await state.set_state(BookingStates.MAIN_MENU)



# Handler for showing cancel confirmation
@dp.callback_query(F.data.startswith("ask_cancel:"))
async def ask_cancel_confirmation(callback: types.CallbackQuery):
    appointment_id = callback.data.split(":")[1]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Yes, cancel", callback_data=f"confirm_cancel:{appointment_id}")],
            [InlineKeyboardButton(text="↩️ No, go back", callback_data="cancel_back")]
        ]
    )
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


# Handler for confirming cancellation
@dp.callback_query(F.data.startswith("confirm_cancel:"))
async def process_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup()  # Убираем inline-кнопки
    appointment_id = callback.data.split(":")[1]
    cursor.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
    conn.commit()

    await callback.message.edit_text("✅ Appointment successfully canceled.")
    await callback.answer()


# Handler for "No, go back" button
@dp.callback_query(F.data == "cancel_back")
async def cancel_back(callback: types.CallbackQuery):
    await callback.message.edit_reply_markup()
    await callback.answer("Cancellation cancelled.")


async def reminder_loop():
    while True:
        now = datetime.now()
        cursor.execute("""
            SELECT id, user_id, date, time FROM appointments
            WHERE reminded = 0
        """)
        appointments = cursor.fetchall()

        for appt in appointments:
            appt_id, user_id, date_str, time_str = appt
            appt_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            delta = appt_datetime - now

            if timedelta(hours=23, minutes=59) <= delta <= timedelta(hours=24, minutes=1):
                try:
                    await bot.send_message(user_id, f"🔔 Reminder: You have an appointment on {date_str} at {time_str}!")
                    cursor.execute("UPDATE appointments SET reminded = 1 WHERE id = ?", (appt_id,))
                    conn.commit()
                except Exception as e:
                    print(f"❌ Failed to send reminder to {user_id}: {e}")

        await asyncio.sleep(60)  



async def main():
    print("Bot started...")

    dp.include_router(admin_router)
    
    asyncio.create_task(reminder_loop())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())