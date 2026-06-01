import json
import os
import getpass


def main():
    usuario = input("GDIS_USUARIO: ").strip()
    senha = getpass.getpass("GDIS_SENHA: ").strip()
    if not usuario or not senha:
        raise SystemExit("ERRO: usuário e senha são obrigatórios.")
    pasta = os.path.join(os.path.expanduser("~"), ".dashboard_mt")
    os.makedirs(pasta, exist_ok=True)
    path = os.path.join(pasta, "credenciais.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"usuario": usuario, "senha": senha}, f, ensure_ascii=False)
    print(f"OK: credenciais salvas em {path}")


if __name__ == "__main__":
    main()

