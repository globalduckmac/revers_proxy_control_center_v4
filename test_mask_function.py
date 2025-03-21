#!/usr/bin/env python3
"""
Простой тест функции маскирования доменных имен.
"""

def mask_domain_name(domain_name):
    """
    Маскирует часть доменного имени для обеспечения безопасности.
    Например, example.com превращается в exa****.com
    
    Args:
        domain_name (str): Полное имя домена
        
    Returns:
        str: Замаскированное имя домена
    """
    if not domain_name:
        return "unknown"
    
    # Разбиваем домен на части
    parts = domain_name.split('.')
    
    # Если домен слишком короткий, просто маскируем больше символов
    if len(parts[0]) <= 3:
        masked_first_part = parts[0][0] + '*' * (len(parts[0]) - 1)
    else:
        # Оставляем первые 3 символа, остальное заменяем звездочками
        masked_first_part = parts[0][:3] + '*' * (len(parts[0]) - 3)
    
    # Собираем домен обратно
    return '.'.join([masked_first_part] + parts[1:])

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
    
    print("Тестирование функции маскирования доменов")
    print("-" * 50)
    
    for domain in test_domains:
        masked = mask_domain_name(domain)
        print(f"Исходный домен: {domain}")
        print(f"Маскированный: {masked}")
        print("-" * 30)
    
    print("Тестирование завершено")

if __name__ == "__main__":
    test_domain_masking()