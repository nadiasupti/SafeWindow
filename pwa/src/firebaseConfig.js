// The web app's Firebase settings. These are not secrets: Firebase web apps ship them to every browser,
// and access is controlled by firestore.rules. The Admin key (used by scripts/send_alert.py) is secret and
// never lives in this folder.
export const firebaseConfig = {
  apiKey: 'AIzaSyAOLuevRhT7LzpcfQpy33eHGBmW06dnSto',
  authDomain: 'safewindow-3b759.firebaseapp.com',
  projectId: 'safewindow-3b759',
  storageBucket: 'safewindow-3b759.firebasestorage.app',
  messagingSenderId: '499177825479',
  appId: '1:499177825479:web:ebec7fc088691409b40ae2',
}

// Public "Web Push certificate" key from Firebase Console > Project settings > Cloud Messaging.
// Also not a secret. If it is ever emptied, the app says notifications are not set up.
export const VAPID_KEY = 'BKVe65WEfx6jni3UsMNwwOOVCkPZ7XYcQlxUriF1vfynCZA2vq_wo7JFnE7TQezPFOdgJDF0OPmhjje8Xd_OpsQ'
