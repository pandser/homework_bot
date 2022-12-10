import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv

from exeptions import VariableNotAvailableException, ErrorCodeException


load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


PRACTICUM_TOKEN = os.getenv('PRACTICUM')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """
    Проверка доступности необходимых токенов.
    """
    if not all([True if os.getenv(var) else False
                for var in ('PRACTICUM', 'TG_TOKEN', 'TG_CHAT')]):
        error_message = (
            'Отсутствует одна из обязательных переменных окружения'
        )
        logger.critical(error_message)
        raise VariableNotAvailableException(error_message)


def send_message(bot, message):
    """
    Отправка сообщения телеграм-ботом.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Сообщение отправлено')
    except Exception as error:
        logger.error(f'Сообщение не удалось отправить {error}')


def get_api_answer(timestamp):
    """
    Делает запрос к эндпойнту, в случае успеха возвращает
    ответ в виде словаря.
    """
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp},
        )
        logger.debug('Запрос отпрвлен')
        if response.status_code == requests.codes.ok:
            return response.json()
        else:
            error_message = (
                f'Ошибка при запросе к эндпойту. {response.status_code}'
            )
            logger.error(error_message)
            raise ErrorCodeException(error_message)
    except requests.RequestException as error:
        logger.error(error)


def check_response(response):
    """
    Проверка полученного ответа на соответствие документации.
    """
    if 'homeworks' in response and isinstance(response.get('homeworks'), list):
        if not response.get('homeworks'):
            logger.debug('Домашние задания не найдены')
            return False
        return True
    else:
        raise TypeError('Нет ключа homeworks')


def parse_status(homework):
    """
    Извлекает статус домащней работы.
    """
    if homework.get('homework_name') is None:
        logger.error('В ответе нет ожидаемого поля "homework_name"')
        raise KeyError('В ответе нет ожидаемого поля "homework_name"')
    homework_name = homework.get('homework_name')
    if homework.get('status') not in HOMEWORK_VERDICTS:
        error_message = (
            f'В поле status неожиданное значение {homework.get("status")}'
        )
        logger.error(error_message)
        raise KeyError(error_message)
    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_error_message(bot, error):
    error_message = f'{error}'
    send_message(bot, error_message)
    time.sleep(RETRY_PERIOD)


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    current_status = 'current_status'
    last_error = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            if check_response(response):
                status = parse_status(response.get('homeworks')[0])
                if status != current_status:
                    send_message(bot, status)
                    current_status = status
                logger.debug('Статус не изменился')
            timestamp = response.get('current_date')
            time.sleep(RETRY_PERIOD)

        except KeyError as error:
            if last_error != str(error):
                last_error = str(error)
                send_error_message(bot, error)
            else:
                time.sleep(RETRY_PERIOD)

        except TypeError as error:
            if last_error != str(error):
                last_error = str(error)
                send_error_message(bot, error)
            else:
                time.sleep(RETRY_PERIOD)

        except ErrorCodeException as error:
            if last_error != str(error):
                last_error = str(error)
                send_error_message(bot, error)
            else:
                time.sleep(RETRY_PERIOD)

        except requests.RequestException as error:
            if last_error != str(error):
                last_error = str(error)
                send_error_message(bot, error)
            else:
                time.sleep(RETRY_PERIOD)

        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.critical(msg=error_message)
            send_message(bot, error_message)
            break


if __name__ == '__main__':
    main()
