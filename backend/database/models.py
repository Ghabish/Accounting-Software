"""Import every model module so metadata is complete (Alembic, create_all)."""
from backend.accounting import models as accounting  # noqa: F401
from backend.ap import models as ap  # noqa: F401
from backend.ar import models as ar  # noqa: F401
from backend.assets import models as assets  # noqa: F401
from backend.audit import models as audit  # noqa: F401
from backend.authentication import models as authentication  # noqa: F401
from backend.banking import models as banking  # noqa: F401
from backend.budgeting import models as budgeting  # noqa: F401
from backend.cinema import models as cinema  # noqa: F401
from backend.closing import models as closing  # noqa: F401
from backend.masters import models as masters  # noqa: F401
from backend.tax import models as tax  # noqa: F401
from backend.workflow import models as workflow  # noqa: F401
from backend.database.base import Base  # noqa: F401
