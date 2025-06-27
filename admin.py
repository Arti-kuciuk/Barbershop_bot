from aiogram.fsm.state import StatesGroup, State

# State group for admin cancellation confirmation
class AdminStates(StatesGroup):
    AWAITING_CANCEL_CONFIRMATION = State()
import os
from aiogram.types import Message
from aiogram import F, Router
from dotenv import load_dotenv
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from datetime import datetime, timedelta
import sqlite3


load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_ID")) 

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

router = Router()

admin_menu = ReplyKeyboardBuilder()
admin_menu.button(text="📆 All bookings")
admin_menu.button(text="📅 Bookings by date")
admin_menu.button(text="❌ Cancel booking")
admin_menu.adjust(1)


def get_admin_date_keyboard(mode: str = "view"):
    today = datetime.now().date()
    buttons = []

    valid_days_found = 0
    current_day = today

    while valid_days_found < 7:
        if current_day.weekday() < 6:
            date_str = current_day.strftime("%Y-%m-%d")
            cursor.execute("SELECT COUNT(*) FROM appointments WHERE date = ?", (date_str,))
            count = cursor.fetchone()[0]

            label = f"{current_day.strftime('%d.%m.%Y')} — {count} bookings"
            callback = f"{mode}_date:{date_str}"  # вот тут ключевой момент
            buttons.append([InlineKeyboardButton(text=label, callback_data=callback)])
            valid_days_found += 1

        current_day += timedelta(days=1)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == "/admin")
async def admin_start(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🔐 Welcome to Admin Panel.", reply_markup=admin_menu.as_markup(resize_keyboard=True))
        await state.clear()
    else:
        await message.answer("🚫 You are not authorized to access this section.")


@router.message(F.text == "📆 All bookings")
async def show_all_bookings(message: Message):
    cursor.execute("SELECT * FROM appointments ORDER BY date, time")
    results = cursor.fetchall()

    if results:
        msg = "📋 All appointments:\n\n"
        for row in results:
            msg += f"📅 {row[2]}, ⏰ {row[3]}, 👤 {row[4]}, 📞 {row[5]}\n"
        await message.answer(msg)
    else:
        await message.answer("No appointments found.")

@router.message(F.text == "📅 Bookings by date")
async def show_admin_date_list(message: Message):
    await message.answer(
        "📅 Select a date to view bookings:",
        reply_markup=get_admin_date_keyboard(mode="view")
    )

@router.message(F.text == "❌ Cancel booking")
async def cancel_booking(message: Message):
    await message.answer(
        "❌ Select a booking date to cancel:",
        reply_markup=get_admin_date_keyboard(mode="cancel")
    )



@router.callback_query(F.data.startswith("view_date:"))
async def view_appointments_on_date(callback: CallbackQuery):
    await callback.message.edit_reply_markup()
    date_str = callback.data.split(":")[1]
    cursor.execute("SELECT * FROM appointments WHERE date = ?", (date_str,))
    results = cursor.fetchall()

    if results:
        msg = f"📅 Appointments on {date_str}:\n\n"
        for row in results:
            msg += f"⏰ {row[3]}, 👤 {row[4]}, 📞 {row[5]}\n"
        await callback.message.answer(msg)
    else:
        await callback.message.answer("No bookings found for this date.")
    await callback.answer()



admin_router = router


# --- Admin cancellation handlers ---
from aiogram.types import CallbackQuery

@router.callback_query(F.data.startswith("cancel_date:"))
async def show_bookings_for_cancellation(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":")[1]
    cursor.execute("SELECT * FROM appointments WHERE date = ?", (date_str,))
    results = cursor.fetchall()

    if results:
        for row in results:
            text = f"📅 {row[2]}, ⏰ {row[3]}, 👤 {row[4]}, 📞 {row[5]}"
            cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"admin_cancel:{row[0]}")]
            ])
            await callback.message.answer(text, reply_markup=cancel_btn)
    else:
        await callback.message.answer("No bookings found for this date.")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cancel:"))
async def ask_admin_cancel_confirmation(callback: CallbackQuery, state: FSMContext):
    booking_id = callback.data.split(":")[1]
    await state.update_data(cancel_booking_id=booking_id)

    confirmation_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes", callback_data="admin_confirm_cancel")],
        [InlineKeyboardButton(text="↩️ Go back", callback_data="admin_cancel_back")]
    ])
    await callback.message.edit_reply_markup(reply_markup=confirmation_kb)
    await state.set_state(AdminStates.AWAITING_CANCEL_CONFIRMATION)


@router.callback_query(F.data == "admin_confirm_cancel")
async def confirm_admin_cancel(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    booking_id = data.get("cancel_booking_id")

    if booking_id:
        cursor.execute("DELETE FROM appointments WHERE id = ?", (booking_id,))
        conn.commit()
        await callback.message.edit_text("✅ Booking has been cancelled.")
    else:
        await callback.message.answer("⚠️ Booking not found or already cancelled.")

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "admin_cancel_back")
async def cancel_back_to_booking(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    booking_id = data.get("cancel_booking_id")

    if booking_id:
        cursor.execute("SELECT * FROM appointments WHERE id = ?", (booking_id,))
        booking = cursor.fetchone()
        if booking:
            text = f"📅 {booking[2]}, ⏰ {booking[3]}, 👤 {booking[4]}, 📞 {booking[5]}"
            cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"admin_cancel:{booking_id}")]
            ])
            await callback.message.edit_text(text, reply_markup=cancel_btn)

    await state.clear()
    await callback.answer()
