from research_domain import Researcher, ResearcherController


def seed():
    ctrl = ResearcherController()
    r = Researcher(name="Paulo Sergio dos Santos Junior")
    r.brand_id = "8400407353673370"
    ctrl.create(r)
    print(f"Created researcher: {r.name} (ID: {r.id})")


if __name__ == "__main__":
    seed()
