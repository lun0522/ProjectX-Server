import dlib
import os
import glob
from core import paintingDB
from skimage import io
import mysql.connector
import shutil
import numpy as np
from core.comparator import landmark_map

detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor(paintingDB.predictor_path)


def create_rect(xlo, ylo, xhi, yhi):
    return dlib.rectangle(xlo, ylo, xhi, yhi)


def detect_face(img):
    return [bbox for num, bbox in enumerate(detector(img, 1))]


def detect_landmarks(img, bbox):
    landmarks = np.array([[point.x, point.y] for point in predictor(img, bbox).parts()], dtype=np.float64).transpose()

    for _, (start, end), (left, right), _ in landmark_map:
        leftmost, rightmost = left - start, right - start
        points = landmarks[:, start: end]
        # let the x coordinate of the leftmost point be 0.0
        # let the mean of y coordinates of all points be 0.0
        points -= np.array([points[0][leftmost], np.mean(points[1, :])]).reshape(2, 1)
        # let the x coordinate of the rightmost point be 2.0
        # scale all y coordinates at the same time with the same ratio
        points *= 2.0 / points[0][rightmost]
        # let the x coordinate of the leftmost point be -1.0, and that of the rightmost be 1.0
        points[0, :] -= 1.0

    return np.hstack((landmarks[0, :], landmarks[1, :]))


def detect(directory=paintingDB.downloads_dir):
    if not os.path.exists(paintingDB.paintings_dir):
        os.makedirs(paintingDB.paintings_dir)
    os.chdir(directory)

    try:
        for img_file in sorted(glob.glob("*.jpg")):
            # some images are downloaded, but have invalid file size
            # those < 10KB will be deleted, but the url will be preserved in the Download table
            if os.path.getsize(img_file) < 10240:
                print("Invalid file size: {}".format(img_file))
                os.remove(img_file)
                continue

            title = img_file[:-4]
            img_data = io.imread(img_file)

            # do face detection
            faces = detect_face(img_data)

            # if any face is detected, store its bounding box
            # and do face landmark detection
            if len(faces):
                print("Found {} face(s) in {}".format(len(faces), title))
                url = paintingDB.retrieve_download_url(title)

                if url:
                    # i.e. row number in database
                    painting_id = paintingDB.store_painting_info(url)

                    # store painting id, landmarks points and bounding box for each face
                    for idx, bbox in enumerate(faces):
                        paintingDB.store_landmarks(painting_id, detect_landmarks(img_data, bbox).tolist(),
                                                   (bbox.left(), bbox.right(), bbox.bottom(), bbox.top()))

                    # move the image to paintings folder
                    shutil.move(directory + img_file, paintingDB.get_painting_filename(painting_id))

                # if no url, delete the image
                else:
                    print("No record in database: {}".format(img_file))
                    os.remove(img_file)

            # if no face, delete the image
            else:
                print("No face found in {}".format(title))
                os.remove(img_file)

            paintingDB.remove_redundant_info(title)

        print("Detection finished.")

    except mysql.connector.Error as err:
        print("Error in MySQL: {}".format(err))

    # ensure to save all changes and do double check if necessary
    finally:
        paintingDB.commit_change()
        paintingDB.cleanup()


if __name__ == "__main__":
    detect()
