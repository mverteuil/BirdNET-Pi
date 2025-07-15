from pydantic import BaseModel


class User(BaseModel):
    """Represents a user in the system."""

    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    """Represents a user stored in the database, including their hashed password."""

    hashed_password: str
