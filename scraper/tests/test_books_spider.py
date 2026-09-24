"""Spider callbacks tested against tiny hand-written pages with the same structure as books.toscrape.com.

No network: we build Scrapy Response objects ourselves and check what each callback yields.
If the site's HTML changes, these tell you which selector broke.
"""
from scrapy import Request
from scrapy.http import HtmlResponse

from scrapesearch.items import BookItem
from scrapesearch.spiders.books import BooksSpider

HOME = """
<div class="side_categories"><ul class="nav nav-list">
  <li><a href="catalogue/category/books_1/index.html">Books</a>
    <ul>
      <li><a href="catalogue/category/books/travel_2/index.html">Travel</a></li>
      <li><a href="catalogue/category/books/mystery_3/index.html">Mystery</a></li>
    </ul>
  </li>
</ul></div>
"""

CATEGORY_PAGE = """
<ol class="row">
  <li><article class="product_pod"><h3><a href="../../../book-one_1/index.html" title="Book One">Book One</a></h3></article></li>
  <li><article class="product_pod"><h3><a href="../../../book-two_2/index.html" title="Book Two">Book Two</a></h3></article></li>
</ol>
<ul class="pager"><li class="next"><a href="page-2.html">next</a></li></ul>
"""

LAST_CATEGORY_PAGE = """
<article class="product_pod"><h3><a href="../../../book-three_3/index.html">Book Three</a></h3></article>
<ul class="pager"><li class="previous"><a href="page-1.html">previous</a></li></ul>
"""

BOOK_PAGE = """
<ul class="breadcrumb">
  <li><a href="../../index.html">Home</a></li>
  <li><a href="../category/books_1/index.html">Books</a></li>
  <li><a href="../category/books/poetry_23/index.html">Poetry</a></li>
  <li class="active">A Light in the Attic</li>
</ul>
<div class="item active"><img src="../../media/cache/fe/72/cover.jpg" alt="cover" /></div>
<div class="col-sm-6 product_main">
  <h1>A Light in the Attic</h1>
  <p class="price_color">£51.77</p>
  <p class="instock availability"><i class="icon-ok"></i>
      In stock (22 available)
  </p>
  <p class="star-rating Three"><i class="icon-star"></i></p>
</div>
<div id="product_description" class="sub-header"><h2>Product Description</h2></div>
<p>It's hard to imagine a world without A Light in the Attic. ...more</p>
"""


def make_response(url, body):
    return HtmlResponse(url=url, body=body.encode("utf-8"), encoding="utf-8", request=Request(url))


def test_home_follows_each_category_but_not_the_all_books_link():
    spider = BooksSpider()
    requests = list(spider.parse(make_response("https://books.toscrape.com/", HOME)))

    assert [r.url for r in requests] == [
        "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
    ]
    assert all(r.callback == spider.parse_category for r in requests)


def test_category_page_follows_books_and_next_page():
    spider = BooksSpider()
    url = "https://books.toscrape.com/catalogue/category/books/travel_2/index.html"
    requests = list(spider.parse_category(make_response(url, CATEGORY_PAGE)))

    book_requests = [r for r in requests if r.callback == spider.parse_book]
    next_requests = [r for r in requests if r.callback == spider.parse_category]
    assert [r.url for r in book_requests] == [
        "https://books.toscrape.com/catalogue/book-one_1/index.html",
        "https://books.toscrape.com/catalogue/book-two_2/index.html",
    ]
    assert [r.url for r in next_requests] == [
        "https://books.toscrape.com/catalogue/category/books/travel_2/page-2.html",
    ]


def test_last_category_page_stops_paginating():
    spider = BooksSpider()
    url = "https://books.toscrape.com/catalogue/category/books/travel_2/page-2.html"
    requests = list(spider.parse_category(make_response(url, LAST_CATEGORY_PAGE)))

    assert len(requests) == 1
    assert requests[0].callback == spider.parse_book


def test_book_page_extracts_raw_fields():
    spider = BooksSpider()
    url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    [item] = list(spider.parse_book(make_response(url, BOOK_PAGE)))

    assert isinstance(item, BookItem)
    assert item["url"] == url
    assert item["title"] == "A Light in the Attic"
    assert item["price"] == "£51.77"                    # raw: the pipeline cleans it
    assert item["rating"] == "star-rating Three"
    assert "22 available" in item["availability"]
    assert item["category"] == "Poetry"
    assert item["description"].startswith("It's hard to imagine")
    assert item["image_url"] == "https://books.toscrape.com/media/cache/fe/72/cover.jpg"


def test_book_page_without_description():
    spider = BooksSpider()
    body = BOOK_PAGE.split('<div id="product_description"')[0]
    [item] = list(spider.parse_book(make_response("https://books.toscrape.com/catalogue/x_1/index.html", body)))
    assert item["description"] is None
