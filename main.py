#!/usr/bin/env python3
# pylint: disable=unused-argument, wrong-import-position
# This program is dedicated to the public domain under the CC0 license.

import datetime
import json
import logging

import numpy as np
import pytz
from sklearn.neighbors import BallTree
from telegram import __version__ as TG_VER

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    Defaults,
    filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

data_file = open('salats.json', 'r')
cities = json.load(data_file)
data_file.close()
earth_radius = 6371  # km

weird_cities = [[
    (city['lat_d'] + city['lat_m'] / 60) * np.pi / 180,
    -(city['long_d'] + city['long_m'] / 60) * np.pi / 180
] for city in cities]

bt = BallTree(weird_cities, metric='haversine')

LOCATION, = range(1)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Salam, please send any location to get prayer times/notifications. You may send a new location any time to update location, or use /stop to stop the bot, "
        "in which case you may start again with /start.\nPlease note that we do not store your location as the "
        "program runs entirely in memory.\nSource code available @ github.com/yassineim/salat_times_bot.")
    return LOCATION


async def location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_message.chat_id

    loc = update.message.location

    distances, indices = bt.query([[loc.latitude * np.pi / 180, loc.longitude * np.pi / 180]])

    context.job_queue.run_once(make_times, 0, data=[distances[0][0], indices[0][0]], chat_id=chat_id)
    remove_job_if_exists(str(chat_id), context)
    context.job_queue.run_daily(make_times, time=datetime.time(hour=0, minute=5), data=[distances[0][0], indices[0][0]],
                                chat_id=chat_id, name=str(chat_id))


async def make_times(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    city_index = context.job.data[1]

    new_today = datetime.date.today()

    new_month = new_today.month
    new_day = new_today.day

    city = cities[city_index]

    month = next(month for month in city['months'] if month['month'] == new_month)
    day = next(day for day in month['days'] if day['day'] == new_day)
    salats = day['salats'][0]
    pretty_salats = ""
    for k, v in salats.items():
        pretty_salats += k + ": " + v + "\n"

    await context.bot.send_message(chat_id, disable_notification=context.bot.name == str(chat_id),
                                   text="Closest city (" + "%.2f" % (context.job.data[0] * earth_radius) + " km): " +
                                        city['nom'] + "\n\nTimes for today, " + str(new_today) +
                                        ":\n\n" + pretty_salats + "\nWill notify on every salat for today.\n")

    remove_job_if_exists(str(chat_id) + "fajr", context)
    remove_job_if_exists(str(chat_id) + "dhuhr", context)
    remove_job_if_exists(str(chat_id) + "asr", context)
    remove_job_if_exists(str(chat_id) + "maghrib", context)
    remove_job_if_exists(str(chat_id) + "ishae", context)

    fajr_time = datetime.datetime.combine(new_today, datetime.datetime.strptime(salats['Fajr'], "%H:%M").time())
    dhuhr_time = datetime.datetime.combine(new_today, datetime.datetime.strptime(salats['Dhuhr'], "%H:%M").time())
    asr_time = datetime.datetime.combine(new_today, datetime.datetime.strptime(salats['Asr'], "%H:%M").time())
    maghrib_time = datetime.datetime.combine(new_today, datetime.datetime.strptime(salats['Maghrib'], "%H:%M").time())
    ishae_time = datetime.datetime.combine(new_today, datetime.datetime.strptime(salats['Ishae'], "%H:%M").time())

    context.job_queue.run_once(alarm, fajr_time, chat_id=chat_id, name=str(chat_id) + "_fajr",
                               data="Fajr (" + str(fajr_time) + ")")
    context.job_queue.run_once(alarm, dhuhr_time, chat_id=chat_id, name=str(chat_id) + "_dhuhr",
                               data="Dhuhr (" + str(dhuhr_time) + ")")
    context.job_queue.run_once(alarm, asr_time, chat_id=chat_id, name=str(chat_id) + "_asr",
                               data="Asr (" + str(asr_time) + ")")
    context.job_queue.run_once(alarm, maghrib_time, chat_id=chat_id, name=str(chat_id) + "_maghrib",
                               data="Maghrib (" + str(maghrib_time) + ")")
    context.job_queue.run_once(alarm, ishae_time, chat_id=chat_id, name=str(chat_id) + "_ishae",
                               data="Ishae (" + str(ishae_time) + ")")


async def alarm(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the alarm message."""
    job = context.job
    await context.bot.send_message(job.chat_id, text=f"{job.data}")


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    chat_id = update.effective_message.chat_id

    remove_job_if_exists(str(chat_id), context)
    remove_job_if_exists(str(chat_id) + "_fajr", context)
    remove_job_if_exists(str(chat_id) + "_dhuhr", context)
    remove_job_if_exists(str(chat_id) + "_asr", context)
    remove_job_if_exists(str(chat_id) + "_maghrib", context)
    remove_job_if_exists(str(chat_id) + "_ishae", context)

    await update.message.reply_text(
        "Bye!", reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END


def main() -> None:
    """Run the bot."""

    # Create the Application and pass it your bot's token.
    application = Application.builder().token("__REDACTED__").defaults(
        Defaults(tzinfo=pytz.timezone('Africa/Casablanca'))).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LOCATION: [
                MessageHandler(filters.LOCATION, location),
            ],
        },
        fallbacks=[CommandHandler("stop", stop)],
    )

    application.add_handler(conv_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
