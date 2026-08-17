"""Список исключений: домены и адреса, которые никогда не выгружаются.

Файл ``config/leads_blacklist.txt`` — по записи на строку, ``#`` начинает
комментарий. Запись без ``@`` трактуется как домен и покрывает поддомены;
запись с ``@`` — как конкретный адрес.

Исключения применяются **на экспорте**, а не при сборе: адрес остаётся в базе
(чтобы повторный обход не нашёл его заново как «новый»), но в CSV не попадает.
Сюда же добавляются отписавшиеся.
"""

from __future__ import annotations

from pathlib import Path

from shared.config import leads_blacklist_path
from engine.observability.logger import get_logger

logger = get_logger("leads.blacklist")


class Blacklist:
    """Проверка домена/адреса на попадание в список исключений."""

    def __init__(self, domains: set[str] | None = None, emails: set[str] | None = None):
        self._domains = {d.lower().lstrip(".") for d in (domains or set())}
        self._emails = {e.lower() for e in (emails or set())}

    def __len__(self) -> int:
        return len(self._domains) + len(self._emails)

    @property
    def domains(self) -> set[str]:
        return set(self._domains)

    @property
    def emails(self) -> set[str]:
        return set(self._emails)

    def blocks_domain(self, domain: str) -> bool:
        """True, если домен или любой его родитель в списке."""
        if not domain:
            return False
        candidate = domain.strip().lower().lstrip(".")
        if candidate in self._domains:
            return True
        # example.com в списке блокирует shop.example.com
        parts = candidate.split(".")
        for i in range(1, len(parts)):
            if ".".join(parts[i:]) in self._domains:
                return True
        return False

    def blocks_email(self, email: str) -> bool:
        """True, если адрес указан явно или его домен в списке."""
        if not email:
            return False
        candidate = email.strip().lower()
        if candidate in self._emails:
            return True
        _, _, domain = candidate.partition("@")
        return self.blocks_domain(domain)

    @classmethod
    def load(cls, path: str | Path | None = None) -> Blacklist:
        """Прочитать список из файла. Отсутствующий файл — пустой список."""
        target = Path(path) if path else Path(leads_blacklist_path())
        if not target.exists():
            logger.debug(f"Список исключений не найден ({target}) — работаем без него")
            return cls()

        domains: set[str] = set()
        emails: set[str] = set()
        for line in target.read_text(encoding="utf-8").splitlines():
            entry = line.split("#", 1)[0].strip().lower()
            if not entry:
                continue
            if "@" in entry:
                emails.add(entry)
            else:
                domains.add(entry.lstrip("."))

        logger.info(f"Список исключений: {len(domains)} доменов, {len(emails)} адресов ({target})")
        return cls(domains=domains, emails=emails)


__all__ = ["Blacklist"]
