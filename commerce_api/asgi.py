from commerce_api.application import create_app
from commerce_api.core.config import Settings

app = create_app(Settings())