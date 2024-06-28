import os


SPECTACULAR_SETTINGS = {
    'TITLE': 'Onfido Service API',
    'DESCRIPTION': 'Onfido Service API',
    'TOS': 'https://rehive.com/terms/',
    'CONTACT': {
        "name": "Rehive Support",
        "url": "https://rehive.com/support/",
        "email": "support@rehive.com"
    },
    'VERSION': '1',
    'EXTERNAL_DOCS': {
        "url": "https://docs.rehive.com",
        "description": "Docs portal"
    },

    # List of servers.
    'SERVERS': [
        {"url": os.environ.get(
            'BASE_URL', "https://onfido.services.rehive.com"
        )}
    ],

    # Swagger UI
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'SWAGGER_UI_SETTINGS': {
	    'docExpansion': 'none',
	    'showExtensions': False,
	    'defaultModelRendering': "example",
	    'displayOperationId': True
    },

    # Redoc
    'REDOC_DIST': 'SIDECAR',
    'REDOC_UI_SETTINGS': {
	    'lazyRendering': True,
	    'nativeScrollbars': True,
	    'requiredPropsFirst': True,
	    'showExtensions': True
    },

    # Disable `drf_spectacular.hooks.postprocess_schema_enums` to prevent
    # converting enums into components.
    'POSTPROCESSING_HOOKS': [],

    # Extensions
    'EXTENSIONS_INFO': {
        "x-logo": {
            "url": "https://rehive.com/images/logo.svg",
            "href": "https://rehive.com",
            "altText": "Rehive logo"
        }
    },
}
