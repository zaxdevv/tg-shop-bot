from . import admin, orders, shop

routers = [shop.router, orders.router, admin.router]
