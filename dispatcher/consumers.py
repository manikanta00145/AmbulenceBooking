import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer


logger = logging.getLogger(__name__)


class DispatcherLocationConsumer(AsyncJsonWebsocketConsumer):
    group_name = "dispatch_locations"

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated or user.role != user.Role.DISPATCHER:
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        logger.debug("Dispatcher location socket closed with code %s", close_code)
        if self.scope["user"].is_authenticated:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def location_update(self, event):
        await self.send_json(event["location"])
