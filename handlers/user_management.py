from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import re

# Исправленный импорт
from db import db  # Изменено с database на db
from admin_keyboards import get_admin_menu, get_user_management_keyboard 
from keyboards import get_back_keyboard

router = Router()

