try:
    from research_domain.domain.entities.advisorship import AdvisorshipType

    print("AdvisorshipType members:")
    for member in AdvisorshipType:
        print(f"  {member.name} = {member.value}")
except ImportError:
    print("Could not import AdvisorshipType")
except Exception as e:
    print(f"Error: {e}")
