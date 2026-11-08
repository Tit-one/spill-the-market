from spill_market.examples import examples
from spill_market.models import StudySpec
from spill_market.services import prepare_study
from spill_market.storage import Store


async def test_custom_extraordinary_claim_is_flagged_in_prepared_study(tmp_path):
    spec = StudySpec.model_validate(examples()[0]['spec'])
    spec.product.name = 'My life'
    spec.product.description = "Un produit miracle qui promet l'immortalité"
    spec.product.category = 'physical'
    spec.product.keywords = []
    spec.audience.population = 60
    spec.audience.representatives = 8
    study = await prepare_study(Store(tmp_path),spec)
    credibility = study['product_credibility']
    assert credibility['status']=='extraordinary_unsubstantiated'
    assert credibility['claims'][0]['evidence_status']=='unsubstantiated'
    assert study['research']['coverage']['product_credibility']==credibility
    assert not credibility.get('scientifically_verified',False)


async def test_persona_skepticism_is_diverse_even_in_one_exact_age(tmp_path):
    spec = StudySpec.model_validate(examples()[0]['spec'])
    spec.audience.population = 60
    spec.audience.representatives = 20
    spec.audience.age_min = spec.audience.age_max = 18
    study = await prepare_study(Store(tmp_path),spec)
    assert len({p['skepticism'] for p in study['personas']})>5
    assert all(p['age']==18 and 0<=p['skepticism']<=1 for p in study['personas'])
