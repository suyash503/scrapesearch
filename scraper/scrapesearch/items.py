import scrapy


class BookItem(scrapy.Item):
    """One book from books.toscrape.com.

    The spider fills these with raw strings from the page; CleanBookPipeline turns them into typed values.
    Using an Item (not a plain dict) means a typo like item["prise"] raises a KeyError instead of silently
    adding a new field.
    """

    url = scrapy.Field()
    title = scrapy.Field()
    price = scrapy.Field()         # raw "£51.77"          -> Decimal("51.77")
    rating = scrapy.Field()        # raw "star-rating Three" -> 3
    availability = scrapy.Field()  # raw "In stock (22 available)" -> 22
    category = scrapy.Field()
    description = scrapy.Field()
    image_url = scrapy.Field()
