import logging
import sys
from modules.telegram_notifier import mask_domain_name

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)

def test_domain_masking():
    """
    Тестирует функцию маскирования доменных имен с разными входными данными.
    """
    test_domains = [
        "example.com",
        "subdomain.example.org",
        "very-long-domain-name-for-testing.co.uk",
        "short.io",
        "a.b.c.d.e.info",
        "аномер1.рф",  # кириллический домен
        "xn--80aswg.xn--p1ai",  # punycode
        "домен.онлайн",
        "test123.com",
        "123test.com",
        "t.co"  # очень короткий домен
    ]
    
    logger.info("Тестирование функции маскирования доменов")
    logger.info("-" * 50)
    
    for domain in test_domains:
        masked = mask_domain_name(domain)
        logger.info(f"Исходный домен: {domain}")
        logger.info(f"Маскированный: {masked}")
        logger.info("-" * 30)
    
    # Проверка логирования с маскированием
    for domain in test_domains[:3]:
        logger.info(f"Тестовое логирование с доменом без маскирования: {domain}")
        masked = mask_domain_name(domain)
        logger.info(f"Тестовое логирование с маскированным доменом: {masked}")
        logger.info("-" * 30)

    logger.info("Проверка интеграции маскирования в функции FFPanel (эмуляция)")
    
    # Эмуляция ответа API FFPanel
    ff_domain = {"domain": "secret-domain.com", "id": 12345, "port": "80"}
    
    # Эмуляция логирования при импорте из FFPanel
    domain_name = ff_domain.get("domain")
    masked_domain_name = mask_domain_name(domain_name)
    logger.info(f"Imported new domain {masked_domain_name} from FFPanel (ID: {ff_domain.get('id')})")
    
    # Эмуляция обработки ошибки
    try:
        raise ValueError("Test error")
    except Exception as e:
        error_msg = f"Ошибка при обработке домена {masked_domain_name}: {str(e)}"
        logger.error(error_msg)
    
    logger.info("Тестирование завершено")

if __name__ == "__main__":
    test_domain_masking()