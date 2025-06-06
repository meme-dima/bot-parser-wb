# ... существующий код filters.py ... 

# def filter_product(product, min_price, max_price, min_rating, min_reviews, brand=None):
#     if not (min_price <= product["current_price"] <= max_price):
#         return False
#     if product.get("rating", 0.0) < min_rating:
#         return False
#     if product.get("reviews", 0) < min_reviews:
#         return False
#     if brand and brand.lower() not in product.get("brand", "").lower():
#         return False
#     # Убрал условие, которое мешало сохранению, когда цена чуть выше скидки за отзыв
#     # if product["current_price"] >= product["feedback_discount"]:
#     #     return False
#     return True 

def is_matching_deal(product_data: dict, user_min_price=None, user_max_price=None) -> bool:
    """Проверяет, является ли товар 'выгодной сделкой' и соответствует ли заданному диапазону цен."""
    current_price = product_data.get('current_price', 0.0)
    feedback_discount = product_data.get('feedback_discount', 0.0)

    # 1. Проверяем на "выгодность": скидка за отзыв должна быть больше цены товара.
    # Это основное условие для того, чтобы считать товар "сделкой".
    # Также убедимся, что цена больше нуля, чтобы не было ложных срабатываний на отсутствующих товарах.
    if not (feedback_discount > current_price and current_price > 0):
        return False

    # 2. Проверяем соответствие диапазону цен пользователя (если он задан)
    if user_min_price is not None and current_price < user_min_price:
        return False
    if user_max_price is not None and current_price > user_max_price:
        return False

    # Если товар "выгодный" и вписывается в ценовой диапазон, возвращаем True
    return True 