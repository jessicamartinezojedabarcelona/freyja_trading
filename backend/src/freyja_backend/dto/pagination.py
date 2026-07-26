from pydantic import BaseModel

# The project's only pagination convention (POINT1-API-001): no prior list
# endpoint existed, so this generic envelope is introduced once here and
# reused by every list endpoint, rather than each endpoint inventing its own
# shape.


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
