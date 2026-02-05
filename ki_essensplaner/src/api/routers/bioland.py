"""Bioland products API endpoints."""

from fastapi import APIRouter, Depends

from src.api.auth import verify_token
from src.api.schemas.bioland import BiolandProduct, BiolandProductList
from src.core.database import get_available_products
from src.scrapers.bioland_huesgen import SOURCE_NAME, get_bioland_data_age

router = APIRouter(prefix="/api/bioland", tags=["bioland"])


@router.get("/products", response_model=BiolandProductList)
def get_products(_token: str = Depends(verify_token)) -> BiolandProductList:
    """Get list of currently available Bioland products.

    Returns all products scraped from bioland-huesgen.de with their
    normalized base ingredients for recipe matching.
    """
    products_data = get_available_products(source=SOURCE_NAME)

    products = [
        BiolandProduct(
            id=p["id"],
            source=p["source"],
            product_name=p["product_name"],
            base_ingredient=p.get("base_ingredient"),
            category=p.get("category"),
            scraped_at=p.get("scraped_at"),
        )
        for p in products_data
    ]

    # Get data age
    data_age_days: int | None = None
    age = get_bioland_data_age()
    if age is not None:
        data_age_days = age.days

    return BiolandProductList(
        products=products,
        total_count=len(products),
        data_age_days=data_age_days,
    )
