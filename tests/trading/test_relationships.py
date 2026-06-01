from datetime import date

from src.trading.relationships import (
    PeerBasketDefinition,
    ThemeTaxonomyNode,
    TickerRelationship,
    build_peer_basket_definition,
    build_peer_basket_members,
    relationship_can_be_used_for,
)


def test_relationship_usage_is_explicit():
    rel = TickerRelationship(
        source_ticker="NVDA",
        target_ticker="MU",
        relationship_type="theme_leader",
        confidence=0.8,
        strength_score=0.7,
        allowed_uses=["readthrough", "peer_basket"],
    )

    assert relationship_can_be_used_for(rel, "readthrough") is True
    assert relationship_can_be_used_for(rel, "trade_approval") is False


def test_peer_basket_members_are_deterministic():
    relationships = [
        TickerRelationship("NVDA", "MU", "theme_leader", 0.8, 0.7, ["peer_basket"]),
        TickerRelationship("NVDA", "LITE", "theme_leader", 0.7, 0.6, ["peer_basket"]),
        TickerRelationship("TSLA", "MU", "customer", 0.5, 0.4, ["readthrough"]),
        TickerRelationship("nvda", "MU", "peer", 0.7, 0.5, ["peer_basket"]),
    ]

    assert build_peer_basket_members("NVDA", relationships) == ["LITE", "MU"]


def test_peer_basket_definition_uses_explicit_relationships_only():
    relationships = [
        TickerRelationship("NVDA", "MU", "theme_leader", 0.8, 0.7, ["peer_basket"]),
        TickerRelationship("NVDA", "LITE", "theme_leader", 0.7, 0.6, ["peer_basket"]),
        TickerRelationship("NVDA", "AAOI", "theme_leader", 0.7, 0.6, ["ui_grouping"]),
    ]

    basket = build_peer_basket_definition(
        basket_key="nvda_ai_infra",
        version="v1",
        trade_date=date(2026, 6, 1),
        source_ticker="NVDA",
        relationships=relationships,
        source_refs=["manual_theme_map_v1"],
    )

    assert basket == PeerBasketDefinition(
        basket_key="nvda_ai_infra",
        version="v1",
        trade_date=date(2026, 6, 1),
        members=("LITE", "MU"),
        construction_method="relationship_graph_v1",
        source_refs=("manual_theme_map_v1",),
    )


def test_theme_taxonomy_node_normalizes_parent_and_status():
    node = ThemeTaxonomyNode(
        theme_id="ai_infra",
        display_name="AI Infrastructure",
        parent_theme_id="semiconductors",
        description="Compute and networking beneficiaries.",
    )

    assert node.theme_id == "ai_infra"
    assert node.parent_theme_id == "semiconductors"
    assert node.lifecycle_status == "active"
