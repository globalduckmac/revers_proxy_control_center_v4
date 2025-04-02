#!/usr/bin/env python3
import os

# Путь к файлу шаблона
file_path = 'templates/monitoring/index.html'

# Чтение файла
with open(file_path, 'r') as file:
    content = file.read()

# Замена для серверов
content = content.replace(
    "{% for server in servers|sort(attribute='last_check', reverse=True)|slice(3) %}",
    "{% for server in servers|selectattr('last_check', 'defined')|selectattr('last_check', 'ne', None)|sort(attribute='last_check', reverse=True)|slice(3) %}"
)

# Замена для доменов
content = content.replace(
    "{% for domain in domains|sort(attribute='ns_check_date', reverse=True)|slice(3) %}",
    "{% for domain in domains|selectattr('ns_check_date', 'defined')|selectattr('ns_check_date', 'ne', None)|sort(attribute='ns_check_date', reverse=True)|slice(3) %}"
)

# Запись обновленного контента
with open(file_path, 'w') as file:
    file.write(content)

print(f"Файл {file_path} успешно обновлен!")
