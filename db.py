import sqlite3
from datetime import datetime

-- Таблица пользователей
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    subscription BOOLEAN DEFAULT TRUE,
    purchase_date DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Таблица врачей
CREATE TABLE doctors (
    doctor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    specialization VARCHAR(50) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(20) NOT NULL
);

-- Таблица диалогов
CREATE TABLE dialogs (
    dialog_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(user_id),
    doctor_id INTEGER REFERENCES doctors(doctor_id),
    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    end_time DATETIME,
    status VARCHAR(10) DEFAULT 'active'
);
