import asyncio
import nest_asyncio
import logging
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Настройка логирования
logging.basicConfig(
    filename='bot.log', filemode='a',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
BUG_REPORT_GROUP_ID = "-1001234567890"
bug_reports = {}

bot_id = None  # Переменная для хранения ID бота

def parse_double(text: str) -> float:
    try:
        value = float(text)
        if 0 <= value <= 100:
            return value
    except ValueError:
        pass
    return None

def calculate_needed_final_score(midterm: float, endterm: float, target: float) -> float:
    current_score = (midterm * 0.3) + (endterm * 0.3)
    needed_final = (target - current_score) / 0.4
    return max(0, min(needed_final, 100))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global bot_id
    if bot_id is None:
        bot_id = (await context.bot.get_me()).id  # Получаем ID бота
    
    logger.info(f"User {update.effective_user.first_name} started the bot")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton('Ввести оценку за регмид', callback_data='enter_register_midterm')]
    ])
    context.user_data.clear()
    await update.message.reply_text(
        'Привет! Я калькулятор оценок для стипендии и бот для баг-репортов. Выбери, что хочешь сделать!',
        reply_markup=keyboard
    )

async def calc_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'enter_register_midterm':
        await query.message.reply_text("Введи оценку за регмид (от 0 до 100):")
        context.user_data["calc_state"] = "enter_register_midterm"

async def handle_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "calc_state" in context.user_data:
        await handle_calc_input(update, context)

async def handle_calc_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    state = context.user_data["calc_state"]

    if state == "enter_register_midterm":
        value = parse_double(text)
        if value is None or value < 25:
            await update.message.reply_text("Ошибка: введи число от 25 до 100.")
            return
        context.user_data["register_midterm"] = value
        context.user_data["calc_state"] = "enter_register_endterm"
        await update.message.reply_text("Введи оценку за регэнд (от 0 до 100):")
    
    elif state == "enter_register_endterm":
        value = parse_double(text)
        if value is None or value < 25:
            await update.message.reply_text("Ошибка: введи число от 25 до 100.")
            return
        context.user_data["register_endterm"] = value
        avg = (context.user_data["register_midterm"] + context.user_data["register_endterm"]) / 2
        if avg < 50:
            await update.message.reply_text("К сожалению, у тебя летний курс (╯︵╰,)")
            context.user_data.clear()
            return
        context.user_data["calc_state"] = "enter_final_exam"
        await update.message.reply_text("Введи оценку за финальный экзамен (если не сдан, введи 0):")
    
    elif state == "enter_final_exam":
        value = parse_double(text)
        if value is None:
            await update.message.reply_text("Ошибка: введи число от 0 до 100.")
            return
        context.user_data["final"] = value

        midterm = context.user_data["register_midterm"]
        endterm = context.user_data["register_endterm"]
        final_exam = context.user_data["final"]

        if final_exam == 0:
            needed_no_retake = 50.00
            needed_scholarship = calculate_needed_final_score(midterm, endterm, 70)
            needed_higher = calculate_needed_final_score(midterm, endterm, 90)
            result_message = f"Чтобы пройти курс (итог >50), набери на финале: {needed_no_retake:.2f}. (^-^*)\n"
            result_message += f"Для обычной стипендии (>70) нужно: {needed_scholarship:.2f}. (^_^)/\n"
            result_message += f"Для повышенной стипендии (>90) нужно: {needed_higher:.2f}. (>‿<)"
            await update.message.reply_text(result_message)
        else:
            score = (midterm * 0.3) + (endterm * 0.3) + (final_exam * 0.4)
            result_message = f"Твой итоговый балл: {score:.2f}\n"
            if score >= 90:
                result_message += "Поздравляю! Ты получаешь повышенную стипендию! (>‿<)"
            elif score >= 70:
                result_message += "Отлично! Ты получаешь стипендию! (^_^)/"
            elif score >= 50:
                result_message += "Ты не пересдаешь экзамен (^-^*)"
            else:
                result_message += "К сожалению, тебе придется пересдать экзамен (╯︵╰,)"
            await update.message.reply_text(result_message)
        context.user_data.clear()

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global bot_id
    if bot_id is None:
        bot_id = (await context.bot.get_me()).id
    
    chat_id = update.message.chat_id
    text = update.message.text
    user_id = update.effective_user.id

    if chat_id == int(BUG_REPORT_GROUP_ID) and user_id != bot_id:
        if update.message.reply_to_message:
            reply_to_message_id = update.message.reply_to_message.message_id
            if reply_to_message_id in bug_reports:
                report = bug_reports.pop(reply_to_message_id)
                await context.bot.send_message(chat_id=report['chat_id'], text=f"Ответ от разработчиков: {text}")

async def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(calc_callback_handler))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT, handle_private_text))
    application.add_handler(MessageHandler(filters.Chat(int(BUG_REPORT_GROUP_ID)), handle_group_message))
    logger.info("Bot started polling...")
    await application.run_polling()

if __name__ == '__main__':
    nest_asyncio.apply()
    asyncio.run(main())
