import sqlite3
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from email.mime.text import MIMEText
import smtplib
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
# Configuración del bot y correo
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
EMAIL_FROM = os.getenv('EMAIL_FROM')
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
EMAIL_TO = os.getenv('EMAIL_TO')

# Ruta completa a la base de datos
DATABASE_PATH = os.getenv('DATABASE_PATH')


# Configuración de logging
logging.basicConfig(level=logging.INFO)
logging.info("Iniciando el bot de registro de llegada...")

# Función para verificar la base de datos
def verificar_base_datos():
    if not os.path.isfile(DATABASE_PATH):
        raise FileNotFoundError("La base de datos no fue encontrada en la ruta especificada.")

# Función para enviar un correo electrónico
def enviar_notificacion_llegada(nombre_conductor, dni):
    mensaje = MIMEText(f"El conductor {nombre_conductor} con DNI {dni} ha llegado y está listo para ingresar al predio.")
    mensaje['Subject'] = 'Notificación de Llegada de Conductor'
    mensaje['From'] = SMTP_USER
    mensaje['To'] = EMAIL_TO

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, EMAIL_TO, mensaje.as_string())

# Función para manejar el inicio
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    user_data.clear()  # Limpiar datos previos del usuario
    user_data['espera_respuesta'] = 'confirmacion'
    await update.message.reply_text(
        "Bienvenido al sistema de registro. ¿Deseas marcar tu llegada para que vigilancia lo tenga en su listado? (Responde 1 para sí o 2 para no)"
    )

# Función para manejar mensajes de texto
async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    mensaje = update.message.text.strip().lower()

    try:
        verificar_base_datos()  # Verificar si la base de datos existe antes de continuar

        if user_data.get('espera_respuesta') == 'confirmacion':
            if mensaje == "1":
                user_data['espera_respuesta'] = 'dni'
                await update.message.reply_text("Por favor, ingresa tu DNI para registrar tu llegada.")
            elif mensaje == "2":
                await update.message.reply_text("Gracias. El bot se cerrará.")
                user_data.clear()  # Limpiar los datos del usuario para terminar la sesión
            else:
                await update.message.reply_text("Por favor responde con 'sí' o 'no'.")

        elif user_data.get('espera_respuesta') == 'dni' and mensaje.isdigit():
            user_data['dni'] = mensaje
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            # Verificar si el DNI ya existe en la tabla de conductores
            c.execute("SELECT id, nombre FROM conductores WHERE dni = ?", (user_data['dni'],))
            conductor = c.fetchone()

            if conductor:
                conductor_id, nombre_conductor = conductor
                c.execute("INSERT INTO ubicaciones (id_conductor, ubicacion) VALUES (?, 'vigilancia')", (conductor_id,))
                conn.commit()
                conn.close()

                enviar_notificacion_llegada(nombre_conductor, user_data['dni'])
                await update.message.reply_text(f"Llegada registrada para {nombre_conductor}. Notificación enviada a vigilancia.")
                user_data.clear()  # Limpiar datos después de registrar la llegada
            else:
                user_data['espera_respuesta'] = 'nombre'
                await update.message.reply_text("DNI no encontrado. Por favor, ingresa tu nombre para registrarte.")

        elif user_data.get('espera_respuesta') == 'nombre':
            user_data['nombre'] = mensaje
            user_data['espera_respuesta'] = 'placa'
            await update.message.reply_text("Por favor, ingresa la placa de tu vehículo.")

        elif user_data.get('espera_respuesta') == 'placa':
            user_data['placa'] = mensaje
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()

            # Registrar el nuevo conductor
            c.execute("INSERT INTO conductores (nombre, dni, placa) VALUES (?, ?, ?)", (user_data['nombre'], user_data['dni'], user_data['placa']))
            conductor_id = c.lastrowid  # Obtener el ID del conductor recién agregado

            # Registrar la llegada en la tabla de ubicaciones
            c.execute("INSERT INTO ubicaciones (id_conductor, ubicacion) VALUES (?, 'vigilancia')", (conductor_id,))
            conn.commit()
            conn.close()

            enviar_notificacion_llegada(user_data['nombre'], user_data['dni'])
            await update.message.reply_text(f"Llegada registrada para {user_data['nombre']}. Notificación enviada a vigilancia.")
            user_data.clear()
        else:
            await update.message.reply_text("Entrada inválida. Intenta nuevamente.")
    
    except FileNotFoundError as e:
        await update.message.reply_text("Error: La base de datos no fue encontrada. Por favor, verifica la ruta y vuelve a intentarlo.")
    except sqlite3.OperationalError as e:
        await update.message.reply_text("Error al acceder a la base de datos. Verifica que la base de datos esté accesible y vuelve a intentarlo.")
    except Exception as e:
        await update.message.reply_text("Ocurrió un error inesperado. Por favor, inténtalo de nuevo.")
        logging.error(f"Error inesperado: {e}")

# Configuración del bot
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    application.run_polling()

if __name__ == "__main__":
    main()
