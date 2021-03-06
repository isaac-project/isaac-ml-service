import base64
import json
import os
import pytest
import main

from fastapi.testclient import TestClient
from main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def xmi_bytes():
    with open("testdata/xmi/1ET5_7_0.xmi", "rb") as in_file:
        xmi_bytes = in_file.read()
    return xmi_bytes


@pytest.fixture()
def mock_instances():
    instance1 = {
        "taskId": "0",
        "itemId": "0",
        "itemPrompt": "mock_prompt",
        "itemTargets": ["one", "two", "three"],
        "learnerId": "0",
        "answer": "two",
        "label": 1
    }
    instance2 = {
        "taskId": "1",
        "itemId": "1",
        "itemPrompt": "mock_prompt2",
        "itemTargets": ["four", "five", "six"],
        "learnerId": "1",
        "answer": "two",
        "label": 1
    }
    instance3 = {
        "taskId": "2",
        "itemId": "2",
        "itemPrompt": "mock_prompt3",
        "itemTargets": ["four", "five", "six"],
        "learnerId": "2",
        "answer": "five",
        "label": 2
    }
    instance4 = {
        "taskId": "2",
        "itemId": "2",
        "itemPrompt": "mock_prompt3",
        "itemTargets": ["four", "five", "six"],
        "learnerId": "2",
        "answer": "five",
        "label": 2
    }
    instances = [instance1, instance2, instance3, instance4]

    for _ in range(10):
        instances.append(instance1)
        instances.append(instance2)
        instances.append(instance3)
        instances.append(instance4)

    # The dicionaries are used to set up ShortAnswerInstance objects.
    return instances


@pytest.fixture()
def predict_instances():
    instance1 = {
        "taskId": "0",
        "itemId": "0",
        "itemPrompt": "mock_prompt",
        "itemTargets": ["one", "two", "three"],
        "learnerId": "0",
        "answer": "two",
    }
    instance2 = {
        "taskId": "1",
        "itemId": "1",
        "itemPrompt": "mock_prompt2",
        "itemTargets": ["two", "three", "four"],
        "learnerId": "1",
        "answer": "two",
    }
    instance3 = {
        "taskId": "2",
        "itemId": "2",
        "itemPrompt": "mock_prompt3",
        "itemTargets": ["four", "five", "six"],
        "learnerId": "2",
        "answer": "five",
    }

    return [instance1, instance2, instance3]


def test_predict(client, xmi_bytes):
    """
    Test the /addInstance endpoint with an example model.

    This test predicts from the default model that sits in the actual onnx
    model directory instead of from a model sitting in the testdata directory.
    That is necessary because the models are loaded from this directory
    to memory while the service is running.
    The default model cannot be taken out of onnx_models directory.
    Otherwise this test will not run anymore.

    :param client: A client for testing.
    :param xmi_bytes: A byte-encoded CAS instance.
    """
    encoded_bytes = base64.b64encode(xmi_bytes)
    instance_dict = {"modelId": "default", "cas": encoded_bytes.decode("ascii")}
    response = client.post("/predict", json=instance_dict)

    assert response.status_code == 200

    # Assert that the value for the predicted class is 1.
    # (because this is the label in the CAS instance).
    assert response.json()["prediction"] == 1

    for cls in response.json()["classProbabilities"]:
        assert 0 <= response.json()["classProbabilities"][cls] <= 1

    for cls in response.json()["features"]:
        assert 0 <= response.json()["features"][cls] <= 1


def test_predict_wrong_model_ID(client, xmi_bytes):
    """
    Test the /predict endpoint with a model ID that is not present in the
    session object dictionary.

    :param client: A client for testing.
    :param xmi_bytes: A byte-encoded CAS instance.
    """
    encoded_bytes = base64.b64encode(xmi_bytes)
    instance_dict = {"modelId": "non-existent", "cas": encoded_bytes.decode("ascii")}
    response = client.post("/predict", json=instance_dict)

    assert response.status_code == 422
    assert (
        json.loads(response.text)["detail"]
        == 'Model with model ID "non-existent" could '
        "not be found in the ONNX model directory. Please train first."
    )


def test_addInstance(client, xmi_bytes):
    """
    Test the /addInstance endpoint with an example instance.

    :param client: A client for testing.
    :param xmi_bytes: A byte-encoded CAS instance.
    """
    encoded_bytes = base64.b64encode(xmi_bytes)
    instance_dict = {"modelId": "default", "cas": encoded_bytes.decode("ascii")}
    response = client.post("/addInstance", json=instance_dict)

    added_to_features = "default" in main.features

    # Clean the main.features dictionary for future tests.
    main.features = {}

    assert added_to_features
    assert response.status_code == 200


def test_addInstance_no_model_ID(client, xmi_bytes):
    """
    Test the /addInstance endpoint with missing model ID.

    :param client: A client for testing.
    :param xmi_bytes: A byte-encoded CAS instance.
    """
    encoded_bytes = base64.b64encode(xmi_bytes)
    instance_dict = {"modelId": "", "cas": encoded_bytes.decode("ascii")}
    response = client.post("/addInstance", json=instance_dict)

    assert response.status_code == 400
    assert (
        json.loads(response.text)["detail"] == "No model ID passed as argument."
        " Please include a model ID."
    )


@pytest.mark.skip("The input has only one item, which cannot be processed by cross validation.")
def test_trainFromCASes(client, xmi_bytes):
    """
    Test the /train_from_CASes endpoint with test data.

    :param client: A client for testing.
    :param xmi_bytes: A byte-encoded CAS instance.
    """
    # Change the onnx model directory for testing purposes.
    main.onnx_model_dir = "testdata"

    # I am using the addInstance endpoint here to create a CAS instance.
    # This is not optimal because this makes this test depend on this endpoint
    # but this is the most natural way to populate the features dictionary.
    encoded_bytes = base64.b64encode(xmi_bytes)
    instance_dict = {
        "modelId": "default_cas_test",
        "cas": encoded_bytes.decode("ascii"),
    }
    client.post("/addInstance", json=instance_dict)
    # Check that main.features has actually been populated.
    assert "default_cas_test" in main.features

    # The actual test of the endpoint happens here.
    instance_dict = {"modelId": "default_cas_test"}
    response = client.post("/trainFromCASes", json=instance_dict)

    # Store states to check whether the file and session object were created.
    path_exists = os.path.exists(
        os.path.join(main.onnx_model_dir, "default_cas_test.onnx")
    )
    metrics_path_exists = os.path.exists(os.path.join("model_metrics", "random_data.json"))
    session_stored = "default_cas_test" in main.inf_sessions

    # Change onnx model directory back and delete test file and inference
    # session object.
    if session_stored:
        del main.inf_sessions["default_cas_test"]
    if path_exists:
        os.remove(os.path.join(main.onnx_model_dir, "default_cas_test.onnx"))
    if metrics_path_exists:
        os.remove(os.path.join("model_metrics", "random_data.json"))
    main.onnx_model_dir = "onnx_models"

    assert response.status_code == 200
    assert path_exists
    assert session_stored


def test_trainFromCASes_missing_CAS_instance(client):
    """
    Test the /train_from_CASes endpoint with missing CAS instance.

    :param client: A client for testing.
    """
    instance_dict = {"modelId": "default"}
    # Pretend that main.features is empty but store its value to put back in later.
    temp_features = main.features
    main.features = {}
    response = client.post("/trainFromCASes", json=instance_dict)
    # Put the original values back into main.clf.
    main.features = temp_features

    assert response.status_code == 422
    assert (
        json.loads(response.text)["detail"] == "No model here with id"
        " default. Add CAS instances first."
    )


def test_trainFromCASes_no_modelID(client):
    """
    Test the /train_from_CASes endpoint with missing model ID.

    :param client: A client for testing.
    """
    instance_dict = {"modelId": ""}
    response = client.post("/trainFromCASes", json=instance_dict)

    assert response.status_code == 400
    assert (
        json.loads(response.text)["detail"] == "No model id passed as"
        " argument. Please include a model ID"
    )


def test_train(client):
    """
    Test the /train endpoint.

    The test makes use of a randomly generated dataset.
    This way no real dataset must be revealed to git.

    :param client: A client for testing.
    """
    # Change the onnx model directory for testing purposes.
    main.onnx_model_dir = "testdata/train_data/onnx"

    instance_dict = {
        "fileName": os.path.join("testdata/train_data", "random_train_data.tsv"),
        "modelId": "random_data",
    }
    response = client.post("/train", json=instance_dict)

    # Store states to check whether the file and session object were created.
    path_exists = os.path.exists(os.path.join(main.onnx_model_dir, "random_data.onnx"))
    metrics_path_exists = os.path.exists(os.path.join("model_metrics", "random_data.json"))
    session_stored = "random_data" in main.inf_sessions

    # Change onnx model directory back and delete test file and inference
    # session object.
    if session_stored:
        del main.inf_sessions["random_data"]
    if path_exists:
        os.remove(os.path.join(main.onnx_model_dir, "random_data.onnx"))
    if metrics_path_exists:
        os.remove(os.path.join("model_metrics", "random_data.json"))
    main.onnx_model_dir = "onnx_models"

    # The assertions are made after the clean-up process on the basis of the
    # stored states. This ensures that cleaning is done in any case.
    assert response.status_code == 200
    assert path_exists
    assert session_stored


def test_trainFromAnswers(client, mock_instances):
    """
    Test the /trainFromAnswers endpoint.

    :param client: A client for testing.
    :param mock_instances: Mock short answer instances
    """
    # Change the onnx model directory for testing purposes.
    main.onnx_model_dir = "testdata/train_data/onnx"
    main.bow_model_dir = "testdata/train_data/bow"

    instance_dict = {
        "instances": mock_instances,
        "modelId": "random_data",
    }
    response = client.post("/trainFromAnswers", json=instance_dict)

    # Store states to check whether the file and session object were created.
    path_exists = os.path.exists(os.path.join(main.onnx_model_dir, "random_data.onnx"))
    bow_path_exists = os.path.exists(os.path.join(main.bow_model_dir, "random_data.json"))
    metrics_path_exists = os.path.exists(os.path.join("model_metrics", "random_data.json"))
    session_stored = "random_data" in main.inf_sessions

    # Delete all files that have been created during training.
    if session_stored:
        del main.inf_sessions["random_data"]
    if path_exists:
        os.remove(os.path.join(main.onnx_model_dir, "random_data.onnx"))
    if bow_path_exists:
        os.remove(os.path.join(main.bow_model_dir, "random_data.json"))
    if metrics_path_exists:
        os.remove(os.path.join("model_metrics", "random_data.json"))

    main.onnx_model_dir = "onnx_models"
    main.bow_model_dir = "bow_models"
    # The assertions are made after the clean-up process on the basis of the
    # stored states. This ensures that cleaning is done in any case.
    assert response.status_code == 200
    assert path_exists
    assert bow_path_exists
    assert metrics_path_exists
    assert session_stored


def test_predictFromAnswers(client, predict_instances):
    """
    Test the /predictFromAnswers endpoint.

    :param client: A client for testing.
    :param mock_instances: Mock short answer instances that do not have labels
    """
    pred_instance_dict = {
        "instances": predict_instances,
        "modelId": "test_pred_data",
    }

    pred_response = client.post("/predictFromAnswers", json=pred_instance_dict)

    assert pred_response.status_code == 200

    response_dict = json.loads(pred_response.content.decode("utf-8"))
    assert response_dict["predictions"][0]["prediction"] == 1
    assert response_dict["predictions"][1]["prediction"] == 1
    assert response_dict["predictions"][2]["prediction"] == 2
