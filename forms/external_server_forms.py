# -*- coding: utf-8 -*-

from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField, TextAreaField, SubmitField, HiddenField
from wtforms.validators import DataRequired, IPAddress, Optional, Length, NumberRange

class ExternalServerForm(FlaskForm):
    """
    Форма для добавления/редактирования внешнего сервера
    """
    name = StringField('Название сервера', validators=[
        DataRequired(message='Название сервера обязательно'),
        Length(min=2, max=255, message='Название должно содержать от 2 до 255 символов')
    ])
    
    ip_address = StringField('IP-адрес', validators=[
        DataRequired(message='IP-адрес обязателен'),
        IPAddress(message='Введите корректный IP-адрес')
    ])
    
    description = TextAreaField('Описание', validators=[
        Optional(),
        Length(max=1000, message='Описание не должно превышать 1000 символов')
    ])
    
    glances_port = IntegerField('Порт Glances API', validators=[
        Optional(),
        NumberRange(min=1, max=65535, message='Порт должен быть в диапазоне от 1 до 65535')
    ], default=61208)
    
    is_active = BooleanField('Активен', default=True)
    
    submit = SubmitField('Сохранить')
    
    def validate_ip_address(self, field):
        """
        Дополнительная валидация IP-адреса
        """
        # Проверка на localhost и другие нежелательные адреса
        invalid_addresses = ['127.0.0.1', '0.0.0.0', 'localhost']
        if field.data in invalid_addresses:
            field.errors.append('Нельзя использовать localhost или другие специальные адреса')
            return False
        return True
        
class ExternalServerTestForm(FlaskForm):
    """
    Форма для тестирования соединения с внешним сервером
    """
    server_id = HiddenField('ID сервера', validators=[DataRequired()])
    submit = SubmitField('Проверить соединение')