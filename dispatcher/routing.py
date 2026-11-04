from django.urls import re_path

from dispatcher.consumers import DispatcherLocationConsumer


websocket_urlpatterns = [
    re_path(r"^ws/locations/$", DispatcherLocationConsumer.as_asgi()),
]
