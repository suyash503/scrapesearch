import scrapy

from scrapesearch.items import BookItem


class BooksSpider(scrapy.Spider):
    """Crawl every category of books.toscrape.com, follow pagination, and scrape each book's detail page.

    Flow: home page -> 50 category pages (-> their 'next' pages) -> ~1000 book pages.
    Run:  cd scraper && scrapy crawl books
    """

    name = "books"
    allowed_domains = ["books.toscrape.com"]  # OffsiteMiddleware drops requests to any other domain
    start_urls = ["https://books.toscrape.com/"]

    def parse(self, response):
        """Home page: follow every category link in the sidebar."""
        # The sidebar is a nested list. The outer <li> is "Books" (everything); the inner <li>s are
        # the individual categories. Selecting only the inner ones avoids crawling the catalogue twice.
        yield from response.follow_all(css="div.side_categories ul li ul li a", callback=self.parse_category)

    def parse_category(self, response):
        """Category listing (20 books per page): follow each book, then the 'next' page if there is one."""
        yield from response.follow_all(css="article.product_pod h3 a", callback=self.parse_book)

        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            # Relative hrefs like "page-2.html" are resolved against the current URL by response.follow.
            yield response.follow(next_page, callback=self.parse_category)

    def parse_book(self, response):
        """Book detail page: grab raw strings only. Cleaning is the pipeline's job."""
        main = response.css("div.product_main")
        yield BookItem(
            url=response.url,
            title=main.css("h1::text").get(),
            price=main.css("p.price_color::text").get(),
            # The rating is only in the CSS class, e.g. class="star-rating Three".
            rating=main.css("p.star-rating::attr(class)").get(),
            # The text is split around an <i> icon, so join all text nodes.
            availability=" ".join(main.css("p.availability::text").getall()),
            # Breadcrumb: Home > Books > <Category> > <Title>. The category is the 3rd <li>.
            category=response.css("ul.breadcrumb li:nth-child(3) a::text").get(),
            # The description is the <p> right after the "Product Description" header. Some books have none.
            description=response.css("#product_description + p::text").get(),
            image_url=response.urljoin(response.css("div.item.active img::attr(src)").get("")),
        )
