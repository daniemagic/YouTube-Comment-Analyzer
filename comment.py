import io
import sys
import json
import subprocess
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from collections import Counter

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set console output encoding to UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def get_channel_id(youtube, channel_input):
    try:
        if 'youtube.com' in channel_input:
            if '/channel/' in channel_input:
                return channel_input.split('/channel/')[1].split('/')[0]
            elif '/user/' in channel_input:
                username = channel_input.split('/user/')[1].split('/')[0]
                response = youtube.channels().list(part='id', forUsername=username).execute()
                return response['items'][0]['id'] if 'items' in response else None
            elif '/c/' in channel_input:
                custom_name = channel_input.split('/c/')[1].split('/')[0]
                response = youtube.search().list(part='id', q=custom_name, type='channel', maxResults=1).execute()
                return response['items'][0]['id']['channelId'] if 'items' in response else None
        elif channel_input.startswith('UC'):
            return channel_input
        else:
            response = youtube.search().list(q=channel_input, type='channel', part='id', maxResults=1).execute()
            return response['items'][0]['id']['channelId'] if 'items' in response else None
    except Exception as e:
        logger.error(f"Error in get_channel_id: {str(e)}")
        return None

def get_uploads_playlist_id(youtube, channel_id):
    try:
        response = youtube.channels().list(part='contentDetails', id=channel_id).execute()
        return response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except Exception as e:
        logger.error(f"Error in get_uploads_playlist_id: {str(e)}")
        return None

def get_last_n_video_ids(youtube, playlist_id, n=3):
    try:
        video_ids = []
        next_page_token = None
        while len(video_ids) < n:
            response = youtube.playlistItems().list(
                part='contentDetails',
                playlistId=playlist_id,
                maxResults=min(n - len(video_ids), 50),
                pageToken=next_page_token
            ).execute()
            video_ids.extend([item['contentDetails']['videoId'] for item in response['items']])
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        return video_ids[:n]
    except Exception as e:
        logger.error(f"Error in get_last_n_video_ids: {str(e)}")
        return []

def get_video_title(youtube, video_id):
    try:
        response = youtube.videos().list(part='snippet', id=video_id).execute()
        return response['items'][0]['snippet']['title']
    except Exception as e:
        logger.error(f"Error in get_video_title: {str(e)}")
        return "Unknown Title"

def get_video_comments(youtube, video_id, max_comments=10):
    try:
        comments = []
        next_page_token = None
        while len(comments) < max_comments:
            response = youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                maxResults=min(max_comments - len(comments), 100),
                pageToken=next_page_token,
                textFormat='plainText',
                order='relevance'
            ).execute()
            comments.extend([item['snippet']['topLevelComment']['snippet']['textDisplay'] for item in response['items']])
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        return comments[:max_comments]
    except Exception as e:
        logger.error(f"Error in get_video_comments: {str(e)}")
        return []

def analyze_sentiment(comment):
    prompt = f"""
    Analyze the sentiment of the following comment and classify it as POSITIVE, NEUTRAL, or NEGATIVE. Only respond with one of these three words.

    Comment: {comment}

    Sentiment:
    """
    try:
        result = subprocess.run(
            ['ollama', 'run', 'mistral'],
            input=prompt,
            capture_output=True,
            check=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        sentiment = result.stdout.strip().upper()
        if sentiment not in ['POSITIVE', 'NEUTRAL', 'NEGATIVE']:
            logger.warning(f"Unexpected sentiment result: {sentiment}")
            return 'NEUTRAL'
        return sentiment
    except Exception as e:
        logger.error(f"Error in analyze_sentiment: {str(e)}")
        return 'NEUTRAL'

def create_prompt(comments, video_title):
    prompt = f"""
    Analyze YouTube comments for the video titled '{video_title}'. Provide a structured summary with the following numbered sections:

    1. Overall Sentiment: Summarize the general mood (positive, neutral, negative) of the comments and highlight specific themes or recurring sentiments.
Include notable likes, dislikes, or emotional responses (e.g., excitement, frustration).
Identify any changes in sentiment as the video progresses or if certain moments receive distinct reactions.
    2. Viewer Engagement and Interaction: Identify how engaged the audience is with the content (e.g., detailed comments, debates, shared personal experiences).
Highlight any replies or discussions where viewers engage with each other.
    3. Questions or Points of Confusion: List common questions or moments where viewers were unclear or confused.
If possible, suggest how the creator can clarify these points in future videos or through pinned comments.
    4. Suggestions for Future Videos: Summarize viewer suggestions for future content, and if there are any patterns or recurring ideas (e.g., requests for specific topics, tutorials, deeper dives).
Offer insights into the types of content viewers seem most interested in based on their suggestions.
    5. Emerging Themes and Trends: Point out any emerging trends in the comments (e.g., viral challenges, trending topics, or social conversations) that the creator could capitalize on.
Include any unexpected insights (e.g., cultural references or shifts in audience demographics).
    6. Creator Improvement Opportunities: Mention any constructive criticism related to video pacing, length, content format, or technical aspects (e.g., audio, lighting) that the creator could improve.
Identify moments where viewers felt the content could be enhanced or changed to improve retention or satisfaction.

    Provide examples of comments in quotes when possible like "insert comment here". If no information for a section, state "No specific information provided." Provide the summary in the specified format, ensuring each section starts with its number and title exactly as shown above. 

    Comments to analyze:
    {comments}

   Analyze YouTube comments for the video titled '{video_title}'. Provide a structured summary with the following numbered sections:

    1. Overall Sentiment: Summarize the general mood (positive, neutral, negative) of the comments and highlight specific themes or recurring sentiments.
Include notable likes, dislikes, or emotional responses (e.g., excitement, frustration).
Identify any changes in sentiment as the video progresses or if certain moments receive distinct reactions.
    2. Viewer Engagement and Interaction: Identify how engaged the audience is with the content (e.g., detailed comments, debates, shared personal experiences).
Highlight any replies or discussions where viewers engage with each other.
    3. Questions or Points of Confusion: List common questions or moments where viewers were unclear or confused.
If possible, suggest how the creator can clarify these points in future videos or through pinned comments.
    4. Suggestions for Future Videos: Summarize viewer suggestions for future content, and if there are any patterns or recurring ideas (e.g., requests for specific topics, tutorials, deeper dives).
Offer insights into the types of content viewers seem most interested in based on their suggestions.
    5. Emerging Themes and Trends: Point out any emerging trends in the comments (e.g., viral challenges, trending topics, or social conversations) that the creator could capitalize on.
Include any unexpected insights (e.g., cultural references or shifts in audience demographics).
    6. Creator Improvement Opportunities: Mention any constructive criticism related to video pacing, length, content format, or technical aspects (e.g., audio, lighting) that the creator could improve.
Identify moments where viewers felt the content could be enhanced or changed to improve retention or satisfaction.

    Provide examples of comments in quotes when possible like "insert comment here". If no information for a section, state "No specific information provided." Provide the summary in the specified format, ensuring each section starts with its number and title exactly as shown above.

    """
    return prompt

def analyze_comments(comments, video_title):
    prompt = create_prompt(comments, video_title)
    try:
        result = subprocess.run(
            ['ollama', 'run', 'mistral'],
            input=prompt,
            capture_output=True,
            check=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        output = result.stdout.strip()
        logger.debug(f"Ollama output: {output}")
        return output
    except FileNotFoundError:
        error_msg = "Error: 'ollama' command not found. Please ensure Ollama is installed and added to your system PATH."
        logger.error(error_msg)
        return error_msg
    except subprocess.CalledProcessError as e:
        error_msg = f"Error during summarization: {str(e)}"
        logger.error(error_msg)
        return error_msg

def parse_analysis(summary):
    # Split the summary into sections
    sections = summary.split('\n')
    
    # Initialize variables to store each section's content
    current_section = ''
    parsed_result = {
        'overallSentiment': '',
        'viewerEngagement': '',
        'questionsOrConfusion': '',
        'suggestionsForFutureVideos': '',
        'emergingThemes': '',
        'creatorImprovementOpportunities': ''
    }
    
    # Define a mapping of possible section headers to keys
    section_headers = {
        '1. Overall Sentiment': 'overallSentiment',
        '2. Viewer Engagement and Interaction': 'viewerEngagement',
        '3. Questions or Points of Confusion': 'questionsOrConfusion',
        '4. Suggestions for Future Videos': 'suggestionsForFutureVideos',
        '5. Emerging Themes and Trends': 'emergingThemes',
        '6. Creator Improvement Opportunities': 'creatorImprovementOpportunities'
    }
    
    # Iterate through the sections and assign content to the appropriate key
    for line in sections:
        line = line.strip()
        if not line:
            continue
        
        # Check if the line starts with any of the section headers
        found_header = False
        for header, key in section_headers.items():
            if line.startswith(header):
                current_section = key
                # Remove the header from the line
                content = line[len(header):].lstrip(':').strip()
                if content:
                    parsed_result[current_section] += content + ' '
                found_header = True
                break
        
        if not found_header and current_section:
            # If it's not a header and we're in a section, add the line to the current section
            parsed_result[current_section] += line + ' '
    
    # Trim whitespace from all sections
    for key in parsed_result:
        parsed_result[key] = parsed_result[key].strip()
        if not parsed_result[key]:
            parsed_result[key] = 'No specific information provided.'
    
    # Log the parsed result for debugging
    logger.debug(f"Parsed analysis result: {parsed_result}")
    
    return parsed_result

def get_word_cloud_data(comments):
    words = ' '.join(comments).lower().split()
    word_counts = Counter(words)
    total_words = sum(word_counts.values())
    return [{'text': word, 'value': count / total_words} for word, count in word_counts.most_common(50)]

def main(api_key, channel_input, num_videos, max_comments, include_sentiment, include_word_cloud):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        channel_id = get_channel_id(youtube, channel_input)
        if not channel_id:
            return json.dumps({'error': 'Failed to get channel ID. Please check your input and try again.'})

        uploads_playlist_id = get_uploads_playlist_id(youtube, channel_id)
        if not uploads_playlist_id:
            return json.dumps({'error': 'Failed to get uploads playlist ID.'})

        video_ids = get_last_n_video_ids(youtube, uploads_playlist_id, n=num_videos)
        if not video_ids:
            return json.dumps({'error': 'Failed to get video IDs.'})

        results = []
        for video_id in video_ids:
            title = get_video_title(youtube, video_id)
            comments = get_video_comments(youtube, video_id, max_comments=max_comments)
            
            if not comments:
                results.append({
                    'title': title,
                    'error': 'No comments found for this video.'
                })
                continue

            comments_text = '\n'.join(comments)
            summary = analyze_comments(comments_text, title)

            logger.debug(f"Raw summary for video '{title}': {summary}")

            if not summary or 'error' in summary.lower():
                results.append({
                    'title': title,
                    'error': summary if summary else 'No summary was generated for this video.'
                })
                continue

            analysis_result = parse_analysis(summary)
            analysis_result['title'] = title

            if include_sentiment:
                sentiment_counts = Counter(analyze_sentiment(comment) for comment in comments)
                total_comments = sum(sentiment_counts.values())
                analysis_result['sentimentData'] = {
                    'positive': sentiment_counts['POSITIVE'] / total_comments * 100,
                    'neutral': sentiment_counts['NEUTRAL'] / total_comments * 100,
                    'negative': sentiment_counts['NEGATIVE'] / total_comments * 100
                }

            if include_word_cloud:
                analysis_result['wordCloudData'] = get_word_cloud_data(comments)

            results.append(analysis_result)

        logger.info(f"Final results: {results}")
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return json.dumps({'error': f'An unexpected error occurred: {str(e)}'})

if __name__ == '__main__':
    if len(sys.argv) != 7:
        print(json.dumps({'error': "Usage: python comment.py <api_key> <channel_input> <num_videos> <max_comments> <include_sentiment> <include_word_cloud>"}))
        sys.exit(1)

    api_key = sys.argv[1]
    channel_input = sys.argv[2]
    num_videos = int(sys.argv[3])
    max_comments = int(sys.argv[4])
    include_sentiment = sys.argv[5].lower() == 'true'
    include_word_cloud = sys.argv[6].lower() == 'true'

    result = main(api_key, channel_input, num_videos, max_comments, include_sentiment, include_word_cloud)
    logger.info(f"Final output: {result}")
    print(result)