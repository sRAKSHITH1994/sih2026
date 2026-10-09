import numpy as np

from app.lstm_autoencoder import NumpyLSTMAutoencoder


def test_lstm_training_changes_weights_and_scores_large_shift():
    rng=np.random.default_rng(7)
    t=np.linspace(0,12,260)
    normal=np.column_stack((25+np.sin(t),1010+.4*np.cos(t),65+2*np.sin(t/2)))+rng.normal(0,[.03,.03,.08],(260,3))
    model=NumpyLSTMAutoencoder(sequence_length=12,input_dim=3,hidden_dim=6,seed=7)
    before=model.params["Wenc"].copy()
    model.fit(normal,epochs=4,batch_size=32,learning_rate=.003)
    assert not np.allclose(before,model.params["Wenc"])
    normal_score=model.score(normal[-12:])["loss"]
    shifted=normal[-12:].copy();shifted[-4:,0]+=15
    assert model.score(shifted)["loss"]>normal_score


def test_exact_shapley_is_normalized_and_names_all_channels():
    rng=np.random.default_rng(12)
    sequence=rng.normal(size=(80,2))
    model=NumpyLSTMAutoencoder(sequence_length=12,input_dim=2,hidden_dim=4,seed=12)
    model.fit(sequence,epochs=2,batch_size=16,learning_rate=.003)
    report=model.exact_shapley(sequence[-12:])
    assert report["method"]=="exact_shapley_feature_coalitions"
    assert set(report["importance"])=={"temperature_c","pressure_hpa"}
    assert np.isclose(sum(report["importance"].values()),1.0)
