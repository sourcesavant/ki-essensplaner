"""Bioland products API schemas."""

from pydantic import BaseModel


class BiolandProduct(BaseModel):
    """Single Bioland product entry."""

    id: int
    source: str
    product_name: str
    base_ingredient: str | None = None
    category: str | None = None
    scraped_at: str | None = None


class BiolandProductList(BaseModel):
    """List of Bioland products."""

    products: list[BiolandProduct]
    total_count: int
    data_age_days: int | None = None


class BiolandRefreshResponse(BaseModel):
    """Response after refreshing Bioland data."""

    success: bool
    products_found: int
    products_saved: int
    normalized: bool
