from enum import Enum

from pydantic import BaseModel


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class PageInfo(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
