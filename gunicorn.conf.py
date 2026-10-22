# Configuración de gunicorn (Render la lee sola con "gunicorn main:app"). 22/10/2026.
# Antes corría 1 proceso que atendía UN pedido a la vez: si alguien abría un reporte pesado, el buscador de
# productos, guardar cliente o guardar cotización se quedaban esperando y parecía que "no hacían nada".
# Ahora 1 proceso con 8 hilos atiende varios pedidos a la vez sin gastar más memoria del plan.
import os

workers = int(os.environ.get('WEB_CONCURRENCY', '1'))
worker_class = 'gthread'
threads = int(os.environ.get('GUNICORN_THREADS', '8'))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))
graceful_timeout = 30
keepalive = 5
bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
accesslog = '-'
errorlog = '-'
loglevel = 'info'
