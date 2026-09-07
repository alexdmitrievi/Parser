"""Фикстуры тестов домена leads."""

from __future__ import annotations

import pytest

from leads.profiles import Limits, Profile, ProfileConfig


@pytest.fixture
def petcoke_profile() -> Profile:
    return Profile(
        name="petcoke_anode",
        keywords_en=["calcined petroleum coke", "CPC", "anode grade coke", "calcining plant"],
        keywords_zh=["煅烧石油焦", "预焙阳极"],
        hs_codes=["2713.12"],
        target_industries=["aluminium", "graphite electrode", "carbon"],
    )


@pytest.fixture
def profile_config(petcoke_profile: Profile) -> ProfileConfig:
    return ProfileConfig(
        profiles={petcoke_profile.name: petcoke_profile},
        regions_priority=["Shandong", "Hebei", "Henan"],
        limits=Limits(max_pages_per_query=2, request_delay_seconds=0.0, max_concurrency=1),
    )


@pytest.fixture
def catalog_html() -> str:
    """Страница выдачи made-in-china (актуальная разметка hot-china-products)."""
    return """
    <html><body>
      <div class="products-item">
        <a href="https://hongyun.en.made-in-china.com">Shandong Hongyun Carbon Co., Ltd.</a>
        <div>calcined petroleum coke for aluminium smelters, Zibo, Shandong, China</div>
      </div>
      <div class="products-item">
        <a href="https://jiongtaicnc.en.made-in-china.com">Zhejiang Jiongtai Numerical Control Equipment Co., Ltd.</a>
        <div>Zhejiang, China</div>
      </div>
      <div class="products-item">
        <div>карточка без названия</div>
      </div>
    </body></html>
    """


@pytest.fixture
def contact_html() -> str:
    """Контактная страница со всеми формами записи адресов."""
    return """
    <html><body>
      <h1>联系我们 Contact Us</h1>
      <p>Email: <a href="mailto:Sales@Hongyun-Carbon.CN">Sales@Hongyun-Carbon.CN</a></p>
      <p>Export: export (at) hongyun-carbon (dot) cn</p>
      <p>Trade: trade[at]hongyun-carbon[dot]cn</p>
      <p>Manager: li.wei#hongyun-carbon.cn</p>
      <p>Spelled: zhangwei AT hongyun-carbon DOT cn</p>
      <p>Entity: info&#64;hongyun-carbon&#46;cn</p>
      <p>Junk: noreply@hongyun-carbon.cn, webmaster@example.com, someone@sentry.io</p>
      <p>Partner site built by studio@webdesign-agency.com</p>
      <p>See our page at hongyun-carbon.cn for details</p>
      <img src="logo@2x.png">
      <p>Tel: +86 533 1234 5678 — WeChat: hongyun_export</p>
    </body></html>
    """
