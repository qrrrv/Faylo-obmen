from aiogram import Router, types, F
from aiogram.filters import Command
from database import save_script

router = Router()

@router.message(Command("upload"))
async def cmd_upload(message: types.Message):
    if str(message.from_user.id) != "ВАШ_АДМИН_ID":  # Замените на ваш ID
        await message.answer("❌ У вас нет прав для этой команды")
        return
    
    await message.answer("📤 Отправьте мне файл скрипта")

@router.message(F.document)
async def handle_document(message: types.Message):
    if str(message.from_user.id) != "ВАШ_АДМИН_ID":  # Замените на ваш ID
        return
    
    document = message.document
    file_id = document.file_id
    
    await save_script(file_id, document.file_name)
    
    bot_username = (await message.bot.get_me()).username
    bot_link = f"https://t.me/{bot_username}?start=start"
    
    await message.answer(
        f"✅ Скрипт успешно загружен!\n"
        f"📝 Имя файла: {document.file_name}\n\n"
        f"🔗 Ссылка для пользователей:\n{bot_link}\n\n"
        f"Отправьте эту ссылку пользователям для скачивания скрипта."
    )