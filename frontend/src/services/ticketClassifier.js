import { env, pipeline } from "@huggingface/transformers";

const MODEL_ID = "autodesk-ticket-classifier";

env.allowLocalModels = true;
env.allowRemoteModels = false;
env.localModelPath = "/models/";

let classifierPromise = null;

export async function loadTicketClassifier(progressCallback) {
  if (!classifierPromise) {
    classifierPromise = pipeline(
      "text-classification",
      MODEL_ID,
      {
        device: "wasm",
        dtype: "q8",
        progress_callback: progressCallback,
      }
    ).catch((error) => {
      classifierPromise = null;
      throw error;
    });
  }

  return classifierPromise;
}
