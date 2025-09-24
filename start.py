from aiogram import Router, types
from aiogram.filters import Command
from database import get_latest_script

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    script = await get_latest_script()
    
    if script:
        file_id, file_name = script
        await message.answer_document(
            document=file_id,
            caption=f"📥 Вот ваш скрипт: {file_name}\n\nПриятного использования! 🚀"
        )
    else:
        await message.answer("❌ Скрипт временно недоступен. Обратитесь к администратору.")