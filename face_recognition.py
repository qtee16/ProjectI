import cv2
from facenet_pytorch import MTCNN, InceptionResnetV1, fixed_image_standardization
import torch
from torchvision import transforms
import numpy as np
from PIL import Image
import time

from tracker import Tracker

frame_size = (640,480)
IMG_PATH = './data/test_images'
DATA_PATH = './data'

def trans(img):
    transform = transforms.Compose([
            transforms.ToTensor(),
            fixed_image_standardization
        ])
    return transform(img)

def load_faceslist():
    if device == 'cpu':
        embeds = torch.load(DATA_PATH+'/faceslistCPU.pth')
    else:
        embeds = torch.load(DATA_PATH+'/faceslist.pth')
    names = np.load(DATA_PATH+'/usernames.npy')
    return embeds, names

def inference(model, face, local_embeds, threshold = 3):
    embeds = []
    embeds.append(model(trans(face).to(device).unsqueeze(0)))
    detect_embeds = torch.cat(embeds)
    norm_diff = detect_embeds.unsqueeze(-1) - torch.transpose(local_embeds, 0, 1).unsqueeze(0)
    # print(norm_diff)
    norm_score = torch.sum(torch.pow(norm_diff, 2), dim=1)
    
    min_dist, embed_idx = torch.min(norm_score, dim = 1)
    print(min_dist*power, names[embed_idx])
    # print(min_dist.shape)
    if min_dist*power > threshold:
        return -1, -1
    else:
        return embed_idx, min_dist.double()

def extract_face(box, img, margin=20):
    face_size = 160
    img_size = frame_size
    margin = [
        margin * (box[2] - box[0]) / (face_size - margin),
        margin * (box[3] - box[1]) / (face_size - margin),
    ]
    box = [
        int(max(box[0] - margin[0] / 2, 0)),
        int(max(box[1] - margin[1] / 2, 0)),
        int(min(box[2] + margin[0] / 2, img_size[0])),
        int(min(box[3] + margin[1] / 2, img_size[1])),
    ]
    img = img[box[1]:box[3], box[0]:box[2]]
    face = cv2.resize(img,(face_size, face_size), interpolation=cv2.INTER_AREA)
    face = Image.fromarray(face)
    return face

if __name__ == "__main__":
    prev_frame_time = 0
    new_frame_time = 0
    power = pow(10, 6)
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    print(device)

    model = InceptionResnetV1(
        classify=False,
        pretrained="casia-webface"
    ).to(device)
    model.eval()

    mtcnn = MTCNN(thresholds= [0.7, 0.7, 0.8] ,keep_all=True, device = device)

    tracker = Tracker(150, 30, 5)
    skip_frame_count = 0
    track_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
                    (127, 127, 255), (255, 0, 255), (255, 127, 255),
                    (127, 0, 255), (127, 0, 127), (127, 10, 255), (0, 255, 127)]
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
    embeddings, names = load_faceslist()
    while cap.isOpened():
        isSuccess, frame = cap.read()
        if isSuccess:
            centers = []
            boxes, _ = mtcnn.detect(frame)
            if boxes is not None:
                for res in boxes:
                    bbox = list(map(int, res.tolist()))
                    x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
                    centers.append([(x1 + x2) / 2, (y1 + y2) / 2])
                centers = np.array(centers)
                for box in boxes:
                    bbox = list(map(int,box.tolist()))
                    face = extract_face(bbox, frame)
                    idx, score = inference(model, face, embeddings)
                    if idx != -1:
                        frame = cv2.rectangle(frame, (bbox[0],bbox[1]), (bbox[2],bbox[3]), (0,0,255), 2)
                        score = torch.Tensor.cpu(score[0]).detach().numpy()*power
                        frame = cv2.putText(frame, names[idx], (bbox[0],bbox[1]), cv2.FONT_HERSHEY_DUPLEX, 1, (0,255,0), 1, 1)
                    else:
                        frame = cv2.rectangle(frame, (bbox[0],bbox[1]), (bbox[2],bbox[3]), (0,0,255), 2)
                        frame = cv2.putText(frame,'Unknown', (bbox[0],bbox[1]), cv2.FONT_HERSHEY_DUPLEX, 1, (0,255,0), 1, 1)
                if (len(centers) > 0):
                    tracker.update(centers)
                    for j in range(len(tracker.tracks)):
                        if (len(tracker.tracks[j].trace) > 1):
                            x = int(tracker.tracks[j].trace[-1][0, 0])
                            y = int(tracker.tracks[j].trace[-1][0, 1])
                            tl = (x - 10, y - 10)
                            br = (x + 10, y + 10)
                            cv2.putText(frame, str(tracker.tracks[j].trackId), (x - 10, y - 20), 0, 0.5,
                                        track_colors[j], 2)
                            for k in range(len(tracker.tracks[j].trace)):
                                x = int(tracker.tracks[j].trace[k][0, 0])
                                y = int(tracker.tracks[j].trace[k][0, 1])
                                cv2.circle(frame, (x, y), 1, track_colors[j], -1)
                            cv2.circle(frame, (x, y), 2, track_colors[j], -1)

        cv2.imshow('Face Recognition', frame)
        if cv2.waitKey(1)&0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()