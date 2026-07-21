import getpass
import os
import sys

from freyja_backend.application import auth_service
from freyja_backend.core.database import create_database_engine
from freyja_backend.db.session import create_session_factory, session_scope


def _read_identifier() -> str:
    identifier = os.environ.get("FREYJA_OWNER_IDENTIFIER")
    if identifier:
        return identifier
    return input("Identificador de acceso de la propietaria: ")


def _read_password() -> str:
    env_password = os.environ.get("FREYJA_OWNER_PASSWORD")
    if env_password:
        print(
            "Aviso: usando FREYJA_OWNER_PASSWORD del entorno. Prefiere la entrada "
            "interactiva fuera de automatizaciones controladas.",
            file=sys.stderr,
        )
        return env_password
    return getpass.getpass("Contraseña de la propietaria (no se mostrará en pantalla): ")


def main() -> int:
    identifier = _read_identifier()
    password = _read_password()

    engine = create_database_engine()
    try:
        session_factory = create_session_factory(engine)
        with session_scope(session_factory) as db:
            try:
                user = auth_service.create_owner(db, identifier=identifier, password=password)
            except auth_service.OwnerAlreadyExistsError:
                db.rollback()
                print("La propietaria ya existe. No se realizaron cambios.", file=sys.stderr)
                return 1
            except auth_service.InvalidOwnerDataError as exc:
                db.rollback()
                print(f"Datos inválidos: {exc}", file=sys.stderr)
                return 1

            db.commit()
            print(f"Cuenta de propietaria creada correctamente: {user.identifier}")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
