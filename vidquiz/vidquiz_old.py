import pkg_resources

from xblock.core import XBlock
from xblock.fields import Scope, Integer, String, Field, List
from xblock.fragment import Fragment
from urlparse import urlparse
from xblock.run_script import run_script
from xblock.fragment import Fragment

from django.template import RequestContext
from django.shortcuts import render_to_response
from .utils import render_template, load_resource

import urllib

class QuizQuestion():
    """This object contains the contents of a quiz question/problem."""

    # kind of question being asked
    kind = 'SA'

    # question being asked
    question = ''

    # options from which to grab an answer
    options = []

    # answer(s) to the question can be an array
    answer = []

    # tries left
    tries = 3

    '''
    Constructor takes in a string for the question, an array of choices as answers (for multiple choice and
    checkboxes only), an array of potential answers, the kind of question (text, radio, checkbox),
    and the number of attempts a student has.
    '''
    def __init__(self, kind='text', question='', options=[], answer=[], explanation='', tries=3):
        self.kind = kind
        self.question = question
        self.options = options
        self.answer = answer
        self.explanation = explanation
        self.tries = tries

    ''' For development purposes: Output QuizQuestion variables '''
    def __str__(self):
        return "[Question: " + self.question + ", Kind: " + self.kind + ", Options: " + str(self.options) +\
               ", Answer(s): " + str(self.answer) + ", Explanation: " + str(self.explanation) + ", Result: " + ", Tries: " + str(self.tries) + "]"


class VideoQuiz(XBlock):
    """
    A VideoQuiz object plays a specified video file and at times specified in the quiz file, displays a question which
    the student has to answer. Upon completing or skipping a question, the video resumes playback.
    """

    has_children = False

    display_name = String(
        display_name="Video Quiz",
        help="This name appears in the horizontal navigation at the top of the page",
        scope=Scope.settings,
        default="Video Quiz"
    )

    vq_header = String(
        help="Title to be shown above the video area",
        default="", scope=Scope.content
    )

    vid_url = String(
        help="URL of the video page at the provider",
        default="", scope=Scope.content
    )

    '''
    width = Integer(
        help="Width of the video",
        default=640, scope=Scope.content
    )

    height = Integer(
        help="Height of the video",
        default=480, scope=Scope.content
    )
    '''

    quiz_content = String(
        help="Content of quiz to be displayed",
        default="", scope=Scope.content
    )

    results = []

    answers = List(
        default=[], scope=Scope.user_state,
        help="Answers entered by the student",
    )

    quiz = []
    quiz_cuetimes = []
    index = [0]  # for some reason index = 0 keeps resetting to 0

    def load_quiz(self):
        """Load all questions of the quiz from file located at path."""

        # purge quiz and cue times in case it already contains elements
        del self.quiz[:]
        del self.quiz_cuetimes[:]

        print("Loading quiz ...")

        # grab questions, answers, etc from form
        # for line in self.quiz_content.split(';'):
        for line in self.quiz_content.split('\n'):

            '''
            each line will contain the following:
                trigger time
                question kind (text, radio, checkbox)
                question
                optionA|optionB|optionC
                answerA|answerB
                explanation
            '''

            tmp = line.split(" ~ ")

            # populate trigger times for each question
            self.quiz_cuetimes.append(tmp[0])

            # populate container for quiz questions
            #self.quiz.append(QuizQuestion(tmp[1], tmp[2], tmp[3].split("|"), tmp[4].split("|"), tmp[5], int(tmp[6])))
            self.quiz.append(QuizQuestion(tmp[1], tmp[2], tmp[3].split("|"), tmp[4].split("|"), tmp[5]))  # ignore tries
            # Populate array of results for this session
            if len(self.results) < len(self.quiz):
                self.results.append(0)

    @XBlock.json_handler
    def get_to_work(self, data, suffix=''):
        """Perform the actions below when the module is loaded."""

        # return cue time triggers and tell whether or not the quit was loaded
        return {
                "vid_url": self.vid_url, "cuetimes": self.quiz_cuetimes,
                "correct": self.runtime.local_resource_url(self, 'public/img/correct-icon.png'),
                "incorrect": self.runtime.local_resource_url(self, 'public/img/incorrect-icon.png'),
                }

    def grab_current_question(self):
        """Return data relevant for each refresh of the quiz form."""

        content = {
            "index": self.index[0],
            "question": self.quiz[self.index[0]].question,
            "kind": self.quiz[self.index[0]].kind,
            "options": self.quiz[self.index[0]].options,
            "answer": self.quiz[self.index[0]].answer,  # originally blank to prevent cheating
            "student_tries": self.quiz[self.index[0]].tries,
            "result": self.results[self.index[0]],
            "noquiz": False
        }

        ''' Old code; intended to prevent students from grabbing the answer if they did not answer correctly

        # Send out answers ONLY IF the student answered correctly
        if self.results[self.index[0]] == 5:
            content["answer"] = self.quiz[self.index[0]].answer
        else:
            content["answer"] = "if you see this, you cheated! begone!"

        '''

        return content

    @XBlock.json_handler
    def grab_grade(self, data, suffix=''):
        """Return student grade for questions answered throughout video playback"""

        # process grade only if there is a quiz
        if self.quiz_content != "":

            content = {"grade": 0, "total": len(self.results)}

            for i in self.results:
                if i == 5:  # only take into account passed state
                    content["grade"] += 1

            # content["grade"] *= (100.0/len(self.results))  # use this for percentage grade

        else:

            content = {"grade": -1, "total": -1}

        return content

    @XBlock.json_handler
    def grab_explanation(self, data, suffix=''):
        """Return explanation for current question"""

        print("explaining")
        print(self.index[0])

        return {"explanation": self.quiz[self.index[0]].explanation}

    def answer_validate(self, left, right):
        """Validate student answer and return true if the answer is correct, false otherwise."""

        result = False

        if self.quiz[self.index[0]].kind == "text":

            if left.upper() in right[0].upper():
                result = True

        if self.quiz[self.index[0]].kind == "radio":

            if left != "blank":

                # Grab only the first answer in the array returned; prevent cheating
                if left[0]['value'] in right:
                    result = True

        if self.quiz[self.index[0]].kind == "checkbox":

            new_left = []
            for x in left:
                new_left.append(x['value'])

            result = new_left == right

        return result

    @XBlock.json_handler
    def answer_submit(self, data, suffix=''):
        """Accept, record and validate student input, and generate a mark."""

        '''
            Question states being used below:
               0 = student did not touch this question yet
               1 = failed, with tries left
               2 = tries ran out; will fail; used for initial feedback; will be set to 4 afterwards
               3 = passed; used for initial feedback; will be set to 5 afterwards
               4 = failed, with no tries left
               5 = passed
        '''

        print(self.index[0])

        # make sure the question is of a familiar kind
        if self.quiz[self.index[0]].kind in ["text", "radio", "checkbox"]:

            # record student answers; might be useful for professors
            self.answers.append([self.index[0], data["answer"]])

            # are there any tries left?
            if self.quiz[self.index[0]].tries > 0:

                # glitch/cheat avoidance here
                if not self.results[self.index[0]] > 1:

                    # decrease number of tries
                    self.quiz[self.index[0]].tries -= 1

                    # student enters valid answer(s)
                    if self.answer_validate(data["answer"], self.quiz[self.index[0]].answer):
                        self.results[self.index[0]] = 3
                    # student enters invalid answer, but may still have tries left
                    else:
                        self.results[self.index[0]] = 1

        else:
            print("Unsupported kind of question in this quiz.")

        # If the tries ran out, mark this answer as failed
        if self.quiz[self.index[0]].tries == 0 and self.results[self.index[0]] == 1:
            self.results[self.index[0]] = 2

        content = self.grab_current_question()

        # mark this question as attempted, after preparing output
        # ensures student is not alerted too early of completing the question in the past
        if self.results[self.index[0]] in range(2, 4):
            self.results[self.index[0]] += 2  # set to state 4 (failed) or 5 (passed)

        return content

    @XBlock.json_handler
    def index_goto(self, data, suffix=''):
        """Retrieve index from JSON and return quiz question strings located at that index."""

        if len(self.quiz) > 0:
            self.index[0] = data['index']
            return self.grab_current_question()

        else:
            return {"noquiz": True}

    @XBlock.json_handler
    def quiz_reset(self, data, suffix=''):
        """Reset quiz results"""

        self.index[0] = 0

        for i in range(0, len(self.results)):
            self.results[i] = 0
            self.quiz[i].tries = 3

        return {}

    @XBlock.json_handler
    def studio_submit(self, data, suffix=''):
        """
        Studio only: Accepts course author input if any (no validation), and updates fields to contain current data.
        """

        # if some data is sent in, update it
        if len(data) > 0:

            # There is no validation! Enter your data carefully!
            self.vq_header = data["vq_header"]
            self.display_name = data["vq_header"]
            self.quiz_content = data["quiz_content"]
            self.vid_url = data["vid_url"]
            # self.height = data["height"]
            # self.width = data["width"]

            print("submitted data")
            print("Title: " + data["vq_header"])
            print("Quiz data: " + data["quiz_content"])
            print("Video URL: " + data["vid_url"])
            # print("Video size: " + data["width"] + "x" + data["height"] + "px")

            # Reset VidQuiz variables
            self.results = []
            self.quiz = []
            self.quiz_cuetimes = []

        # prepare current module parameters for return
        content = {
            "vq_header": self.vq_header,
            "quiz_content": self.quiz_content,
            "vid_url": self.vid_url,
            # "width": self.width,
            # "height": self.height,
        }

        return content

    # = edX related stuff ============================================================================================ #

    # TO-DO: change this view to display your data your own way.

    def student_view(self, context=None):
        """
        The primary view of VideoQuiz, shown to students.
        """

        # load contents of quiz if any, otherwise this is just a YouTube video player
        if self.quiz_content != "":
            self.load_quiz()

        print("Loading Student View")
        print("====================")
        print(">> Parameters: ")
        print(self.quiz_content)
        print(self.vid_url)
        # print(self.width)
        # print(self.height)
        print(">> Filled data")
        print("Quiz entries: " + str(self.quiz))
        print("Quiz cue times: " + str(self.quiz_cuetimes))
        print("Answers: " + str(self.answers))
        print("Results: " + str(self.results))

        fragment = Fragment()
        fragment.add_content(render_template('templates/html/vidquiz.html', {'self': self}))
        fragment.add_css(load_resource('static/css/vidquiz.css'))
        fragment.add_javascript(load_resource('static/js/vidquiz.js'))
        fragment.initialize_js('VideoQuiz')

        return fragment

    def studio_view(self, context=None):
        """
        The studio view of VideoQuiz, shown to course authors.
        """

        fragment = Fragment()
        fragment.add_content(render_template('templates/html/vidquiz_studio.html', {'self': self}))
        fragment.add_css(load_resource('static/css/vidquiz_studio.css'))
        fragment.add_javascript(load_resource('static/js/vidquiz_studio.js'))

        fragment.initialize_js('VideoQuizStudio')

        return fragment

    @staticmethod
    def workbench_scenarios():
        """Workbench scenario for development and testing"""
        return [
            ("VideoQuiz", """<vidquiz vq_header="Test VidQuiz" vid_url="https://www.youtube.com/watch?v=CxvgCLgwdNk"
            quiz_content="1 ~ text ~ Is this the last question? ~ yes|no|maybe ~ no ~ this is the first question;2 ~ checkbox ~ Is this the first question? ~ yes|no|maybe ~ no|maybe ~ this is the second question;3 ~ radio ~ Is this the second question? ~ yes|no|maybe ~ no ~ this is the third question"/>"""),
        ]