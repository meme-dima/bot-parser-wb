# ... существующий код filters.py ... 

def filter_product(product, min_price, max_price, min_rating, min_reviews, brand=None):
    if not (min_price <= product["current_price"] <= max_price):
        return False
    if product.get("rating", 0.0) < min_rating:
        return False
    if product.get("reviews", 0) < min_reviews:
        return False
    if brand and brand.lower() not in product.get("brand", "").lower():
        return False
    # Убрал условие, которое мешало сохранению, когда цена чуть выше скидки за отзыв
    # if product["current_price"] >= product["feedback_discount"]:
    #     return False
    return True 