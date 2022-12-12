import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv

from endpoints import PRACTICUM_API
from exceptions import VariableNotAvailableException, ErrorCodeException


load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


PRACTICUM_TOKEN = os.getenv('PRACTICUM')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = PRACTICUM_API
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности необходимых токенов."""
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def send_message(bot, message):
    """Отправка сообщения телеграм-ботом."""
    try:
        logger.debug('Отправка сообщения')
        bot.send_message(TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение отправлено')
    except telegram.TelegramError as error:
        logger.error(f'Сообщение не удалось отправить {error}')


def get_api_answer(timestamp):
    """Делает запрос к эндпойнту, возвращает ответ в виде словаря."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp},
        )
        logger.debug('Запрос отпрвлен')
        if response.status_code == requests.codes.ok:
            try:
                return response.json()
            except ValueError as error:
                logger.error(error)
        else:
            error_message = (
                f'Ошибка при запросе к эндпойту. {response.status_code}'
            )
            logger.error(error_message)
            raise ErrorCodeException(error_message)
    except requests.RequestException as error:
        logger.error(error)


def check_response(response):
    """Проверка полученного ответа на соответствие документации."""
    logger.debug('Проверка ответа от сервера')
    if 'homeworks' in response and 'current_date' in response:
        if isinstance(response.get('homeworks'), list):
            if not response.get('homeworks'):
                logger.debug('Домашние задания не найдены')
                return False
            return True
        else:
            raise TypeError('Неверный тип поля homeworks')
    else:
        raise TypeError('Отсутствуют ожидаемые поля homework или current_date')


def parse_status(homework):
    """Извлекает статус домащней работы."""
    homework_name = homework.get('homework_name')
    if homework_name is None:
        logger.error('В ответе нет ожидаемого поля "homework_name"')
        raise KeyError('В ответе нет ожидаемого поля "homework_name"')
    if homework.get('status') not in HOMEWORK_VERDICTS:
        error_message = (
            f'В поле status неожиданное значение {homework.get("status")}'
        )
        logger.error(error_message)
        raise KeyError(error_message)
    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_last_error(bot, last_error, error):
    """Проверка последней возникшей ошибки."""
    if last_error != str(error):
        send_message(bot, str(error))


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        error_message = (
            'Отсутствует одна из обязательных переменных окружения'
        )
        logger.critical(error_message)
        raise VariableNotAvailableException(error_message)
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

        except KeyError as error:
            check_last_error(bot, last_error, error)
            last_error = str(error)
        except TypeError as error:
            check_last_error(bot, last_error, error)
            last_error = str(error)
        except ErrorCodeException as error:
            check_last_error(bot, last_error, error)
            last_error = str(error)
        except requests.RequestException as error:
            check_last_error(bot, last_error, error)
            last_error = str(error)
        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.critical(msg=error_message)
            send_message(bot, error_message)
            break
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
